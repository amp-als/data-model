"""Durable, exclusive execution reports for rebuild workflows."""
import json
import os
import tempfile


def _sync_directory(directory):
    fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def reserve_rebuild_report(output, report):
    """Reserve the final path before remote writes; leave it in place on failure."""
    directory = os.path.dirname(os.path.abspath(output))
    with open(output, 'x') as handle:
        json.dump(report, handle, indent=2, default=str)
        handle.write('\n')
        handle.flush()
        os.fsync(handle.fileno())
    _sync_directory(directory)


def save_rebuild_report(output, report):
    """Atomically replace a report previously reserved by this execution."""
    directory = os.path.dirname(os.path.abspath(output))
    fd, path = tempfile.mkstemp(prefix='.rebuild-report-', dir=directory)
    try:
        with os.fdopen(fd, 'w') as handle:
            json.dump(report, handle, indent=2, default=str)
            handle.write('\n')
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(path, output)
        _sync_directory(directory)
    finally:
        if os.path.exists(path):
            os.unlink(path)
