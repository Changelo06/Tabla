"""Independent board identities and a recoverable legacy-workflow migration."""
import copy
import json
import uuid
from .board_model import DEFAULT_LISTS, validate_board


class BoardCatalog:
    def __init__(self, store):
        self.store = store

    def boards(self, archived=False):
        return sorted(self.store.records('board', state='archive' if archived else 'active'),
                      key=lambda b: (b.get('board_order', 0), b['title'].casefold(), b['id']))

    def create(self, title, project=None, workflow=None):
        if not title.strip() or len(title.strip()) > 100:
            raise ValueError('Board names must have 1–100 characters.')
        config = copy.deepcopy(workflow or {'version': 1, 'lists': DEFAULT_LISTS})
        config['flexible'] = True
        validate_board(config)
        return self.store.save({'kind': 'board', 'title': title.strip(), 'project': project,
                                'workflow': config, 'board_order': len(self.boards())})

    def default(self, project=None, workflow=None):
        candidates = [b for b in self.boards() if b.get('project') == project]
        if candidates:
            return candidates[0]
        owner = self.store.get(project) if project else None
        return self.create((owner['title'] + ' board')[:100] if owner else 'Personal board', project, workflow)

    def migrate(self):
        if self.store.setting('multi_board_schema') == 1:
            return
        rows = [json.loads(r[0]) for r in self.store.db.execute("SELECT payload FROM records WHERE kind='task'")]
        if rows:
            self.store.backup(self.store.path.with_name('before-multiple-boards.sqlite3'))
        workflow = self.store.setting('task_board', {'version': 1, 'lists': copy.deepcopy(DEFAULT_LISTS)})
        # Store.save joins this transaction, so use a savepoint to keep the whole
        # identity rewrite atomic even when helper methods write records.
        with self.store.atomic():
            mapping = {}
            for task in rows:
                existing = self.store.get(task.get('board')) if task.get('board') else None
                if existing and existing['kind'] == 'board':
                    continue
                project = task.get('project')
                if project not in mapping:
                    mapping[project] = self.default(project, workflow)
                task['board'] = mapping[project]['id']
                task.setdefault('board_list', {'To do': 'todo', 'In progress': 'doing', 'Done': 'done'}.get(task.get('status'), 'todo'))
                column = next((c for c in workflow['lists'] if c['id'] == task['board_list']), None)
                if not column or column['status'] != task.get('status', 'To do'):
                    task['board_list'] = {'To do': 'todo', 'In progress': 'doing', 'Done': 'done'}.get(task.get('status'), 'todo')
                self.store._write(task)
            if not self.boards():
                self.default()
            self.store.set_setting('multi_board_schema', 1)

    def assign(self, record):
        """Route tasks created outside Board without losing their project scope."""
        board = self.store.get(record.get('board')) if record.get('board') else None
        if board and board['kind'] != 'board':
            raise ValueError('Invalid board.')
        if board is None or board.get('deleted'):
            board = self.default(record.get('project'))
        record['board'] = board['id']
        record['project'] = board.get('project')
        workflow = board['workflow']
        ids = {c['id'] for c in workflow['lists'] if record.get('deleted') or record.get('archived') or not c.get('archived')}
        if record.get('board_list') not in ids:
            status = record.get('status', 'To do')
            column = next((c for c in workflow['lists'] if not c.get('archived') and c['status'] == status), None)
            column = column or next(c for c in workflow['lists'] if not c.get('archived'))
            record['board_list'] = column['id']
        return record
