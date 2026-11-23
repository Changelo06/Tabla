"""Persistent single-user board workflow on existing task records."""
import copy
import math
import uuid
from datetime import datetime

DEFAULT_LISTS = [
    {'id': 'todo', 'title': 'To do', 'status': 'To do'},
    {'id': 'doing', 'title': 'In progress', 'status': 'In progress'},
    {'id': 'done', 'title': 'Done', 'status': 'Done'},
]


def validate_board(data):
    if not isinstance(data, dict) or data.get('version') != 1 or not isinstance(data.get('lists'), list) or not 1 <= len(data['lists']) <= 100:
        raise ValueError('Invalid board lists.')
    if 'flexible' in data and type(data['flexible']) is not bool:
        raise ValueError('Invalid board workflow mode.')
    ids = set()
    for item in data['lists']:
        if not isinstance(item, dict) or not isinstance(item.get('id'), str) or not item['id'] or item['id'] in ids:
            raise ValueError('Invalid board list identity.')
        if not isinstance(item.get('title'), str) or not 1 <= len(item['title'].strip()) <= 100:
            raise ValueError('List names must have 1–100 characters.')
        if item.get('status') not in ('To do', 'In progress', 'Done') or type(item.get('archived', False)) is not bool:
            raise ValueError('Invalid board list state.')
        if not data.get('flexible') and item['id'] in ('todo', 'doing', 'done') and item.get('archived'):
            raise ValueError('The standard workflow lists must remain active.')
        expected = {'todo': 'To do', 'doing': 'In progress', 'done': 'Done'}.get(item['id'])
        if not data.get('flexible') and expected and item['status'] != expected:
            raise ValueError('Invalid standard workflow status.')
        ids.add(item['id'])
    if not data.get('flexible') and not {'todo', 'doing', 'done'} <= ids:
        raise ValueError('The standard workflow lists must be retained.')
    if not any(not c.get('archived') for c in data['lists']):
        raise ValueError('Keep at least one active list.')
    active = {c['id'] for c in data['lists'] if not c.get('archived')}
    for item in data['lists']:
        target = item.get('completion_target')
        if target is not None and (not isinstance(target, str) or target not in active or target == item['id']):
            raise ValueError('Choose another active list for completed cards.')


def validate_card(record):
    if record.get('board') is not None and not isinstance(record['board'], str):
        raise ValueError('Invalid board identity.')
    if type(record.get('board_list_archived', False)) is not bool:
        raise ValueError('Invalid card archive state.')
    if record.get('cover') not in (None, 'blue', 'green', 'yellow', 'violet', 'rose', 'gray'):
        raise ValueError('Invalid card cover.')
    if 'board_list' in record and not isinstance(record['board_list'], str):
        raise ValueError('Invalid task list.')
    position = record.get('board_position', 0)
    if type(position) not in (int, float) or not math.isfinite(position):
        raise ValueError('Invalid card position.')
    labels = record.get('task_labels', [])
    if not isinstance(labels, list) or len(labels) > 50:
        raise ValueError('A card can have up to 50 labels.')
    for label in labels:
        if not isinstance(label, dict) or not isinstance(label.get('name'), str) or not 1 <= len(label['name']) <= 80 or label.get('color') not in ('blue', 'green', 'yellow', 'violet', 'rose', 'gray'):
            raise ValueError('Invalid card label.')
    lists = record.get('checklists', [])
    if not isinstance(lists, list) or len(lists) > 30:
        raise ValueError('A card can have up to 30 checklists.')
    for checklist in lists:
        if not isinstance(checklist, dict) or not isinstance(checklist.get('id'), str) or not isinstance(checklist.get('title'), str) or not 1 <= len(checklist['title']) <= 100 or not isinstance(checklist.get('items'), list) or len(checklist['items']) > 1000:
            raise ValueError('Invalid card checklist.')
        for item in checklist['items']:
            if not isinstance(item, dict) or not isinstance(item.get('id'), str) or not isinstance(item.get('text'), str) or len(item['text']) > 5000 or type(item.get('checked')) is not bool:
                raise ValueError('Invalid checklist item.')
    comments = record.get('comments', [])
    if not isinstance(comments, list) or len(comments) > 1000 or any(not isinstance(c, dict) or not isinstance(c.get('text'), str) or len(c['text']) > 10000 or not isinstance(c.get('at'), str) for c in comments):
        raise ValueError('Invalid card activity.')
    for comment in comments:
        datetime.fromisoformat(comment['at'])


class BoardModel:
    def __init__(self, store, board_id=None):
        self.store, self.board_id = store, board_id
        self._config_cache = None

    def config(self):
        if self.board_id:
            if self._config_cache is None:
                board = self.store.get(self.board_id)
                if not board or board['kind'] != 'board':
                    raise ValueError('This board is unavailable.')
                self._config_cache = board['workflow']
            return copy.deepcopy(self._config_cache)
        return self.store.setting('task_board', {'version': 1, 'lists': copy.deepcopy(DEFAULT_LISTS)})

    def lists(self, archived=False):
        return [c for c in self.config()['lists'] if bool(c.get('archived')) == archived]

    def save(self, config):
        validate_board(config)
        if self.board_id:
            board = self.store.get(self.board_id)
            board['workflow'] = config
            self.store.save(board)
            self._config_cache = copy.deepcopy(config)
        else:
            self.store.set_setting('task_board', config)

    def column_for(self, record):
        if self.board_id:
            if self._config_cache is None:
                self.config()
            columns = self._config_cache['lists']
        else:
            columns = self.config()['lists']
        current = next((c for c in columns if c['id'] == record.get('board_list')), None)
        if current and (self.board_id or current['status'] == record.get('status', 'To do')):
            return current['id']
        fallback = {'To do': 'todo', 'In progress': 'doing', 'Done': 'done'}.get(record.get('status'), 'todo')
        return fallback if any(c['id'] == fallback for c in columns) else next(c['id'] for c in columns if not c.get('archived'))

    def cards(self, column, records=None):
        records = self.store.records('task', board=self.board_id) if records is None else records
        if self.board_id:
            records = [r for r in records if r.get('board') == self.board_id]
        return sorted((r for r in records if self.column_for(r) == column), key=lambda r: (r.get('board_position', 0), r.get('created_at', ''), r['id']))

    def add_list(self, title):
        config = self.config()
        item = {'id': str(uuid.uuid4()), 'title': title.strip(), 'status': 'To do'}
        config['lists'].append(item)
        self.save(config)
        return item['id']

    def rename(self, list_id, title):
        config = self.config()
        next(c for c in config['lists'] if c['id'] == list_id)['title'] = title.strip()
        self.save(config)

    def set_completion_target(self, list_id, target):
        config = self.config()
        next(c for c in config['lists'] if c['id'] == list_id)['completion_target'] = target
        self.save(config)

    def route_completion(self, record, previous):
        """Apply a list rule once, on completion; explicit moves take precedence."""
        if record.get('status') != 'Done' or (previous and previous.get('status') == 'Done'):
            return
        if record.get('archived') or record.get('deleted'):
            return
        if previous and (previous.get('board') != record.get('board') or previous.get('board_list') != record.get('board_list')):
            return
        columns = self.lists()
        source = next((c for c in columns if c['id'] == record.get('board_list')), None)
        target = source.get('completion_target') if source else None
        if not target or not any(c['id'] == target for c in columns):
            return
        cards = [c for c in self.cards(target) if c['id'] != record.get('id')]
        record.update(board_list=target, board_position=max((c.get('board_position', 0) for c in cards), default=0) + 1024)

    def move_list(self, list_id, before=None):
        config = self.config()
        item = next(c for c in config['lists'] if c['id'] == list_id)
        config['lists'].remove(item)
        index = next((i for i, c in enumerate(config['lists']) if c['id'] == before), len(config['lists']))
        config['lists'].insert(index, item)
        self.save(config)

    def move_card(self, card_id, list_id, before=None):
        column = next(c for c in self.lists() if c['id'] == list_id)
        record = self.store.get(card_id)
        if card_id == before:
            return record
        if not record or record.get('kind') != 'task' or record.get('deleted') or record.get('archived'):
            raise ValueError('Restore this task before moving it.')
        cards = [c for c in self.cards(list_id) if c['id'] != card_id]
        index = next((i for i, c in enumerate(cards) if c['id'] == before), len(cards))
        lower = cards[index - 1].get('board_position', 0) if index else None
        upper = cards[index].get('board_position', 0) if index < len(cards) else None
        if lower is not None and upper is not None and upper - lower < .000001:
            for i, card in enumerate(cards):
                card['board_position'] = (i + 1) * 1024
                self.store.save(card)
            lower = cards[index - 1]['board_position'] if index else None
            upper = cards[index]['board_position'] if index < len(cards) else None
        position = (lower + upper) / 2 if lower is not None and upper is not None else upper - 1024 if upper is not None else (lower or 0) + 1024
        record.update(board_list=list_id, board_position=position, status=column['status'])
        if self.board_id:
            record['board'] = self.board_id
        return self.store.save(record)

    def archive_list(self, list_id, archived=True):
        if not self.board_id and list_id in ('todo', 'doing', 'done'):
            raise ValueError('Keep the standard workflow lists; archive their cards instead.')
        config = self.config()
        column = next(c for c in config['lists'] if c['id'] == list_id)
        column['archived'] = archived
        if archived:
            for item in config['lists']:
                if item.get('completion_target') == list_id:
                    item['completion_target'] = None
        self.save(config)
        for card in self.store.records('task', state='all', board=self.board_id):
            if card.get('deleted') or self.column_for(card) != list_id:
                continue
            if archived and not card.get('archived'):
                card.update(archived=True, board_list_archived=True)
                self.store.save(card)
            elif not archived and card.get('board_list_archived'):
                card.update(archived=False, board_list_archived=False)
                self.store.save(card)

    def restore_card(self, card_id):
        record = self.store.get(card_id)
        if record and not record.get('deleted'):
            active = {c['id'] for c in self.lists()}
            if self.column_for(record) not in active:
                column = self.lists()[0]
                record.update(board_list=column['id'], status=column['status'])
            record.update(archived=False, board_list_archived=False)
            return self.store.save(record)
