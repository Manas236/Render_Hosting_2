import os
import json
import glob
import logging
import datetime

logger = logging.getLogger(__name__)

_HERE = os.path.dirname(os.path.abspath(__file__))
SOCIAL_DATA_DIR = os.path.join(_HERE, 'social_data')
RUNTIME_DIR = os.path.join(SOCIAL_DATA_DIR, 'runtime')
PERSISTENT_DIR = os.path.join(SOCIAL_DATA_DIR, 'persistent')

# ─────────────────────────────────────────────
# File manifest — runtime vs persistent
# ─────────────────────────────────────────────

# Transient orchestration files — all cleared by reset_social_runtime_state()
RUNTIME_FILES = [
    'run_state.json',         # active stage, in_progress, waiting_for_approval, current_post
    'current_session.json',   # active session identity
    'scheduler_state.json',   # scheduler running flags, next_run
    'lock.json',              # orchestration mutex lock
    'heartbeat.json',         # heartbeat liveness ping
    'queue_processing.json',  # queue drain state
    'failed_run_marker.json', # written on failure, cleared on reset
    'last_send_result.json',  # last batch-extractor "Send to Template" result
]

# Persistent data files — NEVER touched by reset
# social_data/persistent/approved_posts/
# social_data/persistent/captions/
# social_data/persistent/generated_images/
# social_data/persistent/payload_archive/
# social_data/persistent/archive/
# social_data/persistent/posted_history.json
# social_data/persistent/duplicate_protection.json


def ensure_dirs():
    os.makedirs(RUNTIME_DIR, exist_ok=True)
    os.makedirs(PERSISTENT_DIR, exist_ok=True)


def _runtime_path(filename):
    return os.path.join(RUNTIME_DIR, filename)


def read_runtime_file(filename):
    path = _runtime_path(filename)
    if not os.path.exists(path):
        return None
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def write_runtime_file(filename, data):
    ensure_dirs()
    with open(_runtime_path(filename), 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, default=str)


def reset_social_runtime_state():
    """
    Single source of truth for clearing all social pipeline runtime state.

    Removes every file in RUNTIME_FILES plus any stray *.lock files from
    the runtime directory.  Persistent data (posted history, duplicate
    protection, approved posts, etc.) is never touched.

    Returns a dict with keys:
      cleared   — list of filenames that were deleted
      timestamp — UTC ISO-8601 string
    """
    ensure_dirs()
    cleared = []

    for filename in RUNTIME_FILES:
        path = _runtime_path(filename)
        if os.path.exists(path):
            try:
                os.remove(path)
                cleared.append(filename)
                logger.info('[social-reset] cleared runtime state: %s', filename)
            except OSError as e:
                logger.error('[social-reset] failed to remove %s: %s', filename, e)

    for lock_file in glob.glob(os.path.join(RUNTIME_DIR, '*.lock')):
        try:
            os.remove(lock_file)
            name = os.path.basename(lock_file)
            cleared.append(name)
            logger.info('[social-reset] cleared lock file: %s', name)
        except OSError as e:
            logger.error('[social-reset] failed to remove lock file: %s', e)

    logger.info('[social-reset] reset complete — cleared: %s', cleared)
    return {
        'cleared': cleared,
        'timestamp': datetime.datetime.utcnow().isoformat() + 'Z',
    }


def get_pipeline_status():
    """Read all runtime state files and return a unified status dict."""
    run_state = read_runtime_file('run_state.json') or {}
    session = read_runtime_file('current_session.json') or {}
    scheduler = read_runtime_file('scheduler_state.json') or {}
    lock_data = read_runtime_file('lock.json') or {}
    heartbeat = read_runtime_file('heartbeat.json') or {}
    queue = read_runtime_file('queue_processing.json') or {}
    failed = read_runtime_file('failed_run_marker.json') or {}
    send_result = read_runtime_file('last_send_result.json') or {}

    return {
        # Pipeline run
        'stage': run_state.get('stage', 'idle'),
        'waiting_for_approval': run_state.get('waiting_for_approval', False),
        'current_post': run_state.get('current_post'),
        'in_progress': run_state.get('in_progress', False),
        'approval_sent': run_state.get('approval_sent', False),
        # Scheduler
        'scheduler_running': scheduler.get('running', False),
        'scheduler_paused': scheduler.get('paused', False),
        'scheduler_next_run': scheduler.get('next_run'),
        # Session
        'has_active_session': bool(session),
        'session_id': session.get('id'),
        'session_started': session.get('started_at'),
        # Heartbeat
        'heartbeat_alive': heartbeat.get('alive', False),
        'heartbeat_last': heartbeat.get('last_beat'),
        # Lock
        'has_lock': bool(lock_data),
        'lock_owner': lock_data.get('owner'),
        'lock_acquired': lock_data.get('acquired_at'),
        # Queue
        'queue_processing': queue.get('processing', False),
        'queue_size': queue.get('queue_size', 0),
        # Failed run marker
        'has_failed': bool(failed),
        'failed_reason': failed.get('reason'),
        'failed_at': failed.get('failed_at'),
        # Last template send result
        'send_ever_run': bool(send_result),
        'send_timestamp': send_result.get('timestamp'),
        'send_total': send_result.get('total', 0),
        'send_success_count': send_result.get('success_count', 0),
        'send_results': send_result.get('results', []),
        'send_failed': send_result.get('failed', []),
    }


def stop_scheduler():
    """
    Write a stop_requested flag into scheduler_state.json so a running
    scheduler can poll for it and exit cleanly.
    Returns True if the scheduler was running; False if it was already stopped.
    """
    scheduler = read_runtime_file('scheduler_state.json') or {}
    if not scheduler.get('running', False):
        return False
    scheduler['stop_requested'] = True
    scheduler['stop_requested_at'] = datetime.datetime.utcnow().isoformat() + 'Z'
    write_runtime_file('scheduler_state.json', scheduler)
    logger.info('[social-reset] scheduler stop signal written')
    return True
