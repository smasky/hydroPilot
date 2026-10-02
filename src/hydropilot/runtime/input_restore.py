import shutil
import tempfile
from pathlib import Path


class InputRestorer:
    def __init__(self, write_plan):
        self.write_plan = write_plan

    def capture(self, instance_path: str) -> "InputRestoreSnapshot":
        root = Path(instance_path)
        backup_dir = Path(tempfile.mkdtemp(prefix="hydropilot_reset_"))
        files = self._target_files(instance_path)

        try:
            for rel_file in files:
                source = root / rel_file
                if not source.exists():
                    continue
                target = backup_dir / rel_file
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
            return InputRestoreSnapshot(root, backup_dir, files)
        except Exception:
            shutil.rmtree(backup_dir, ignore_errors=True)
            raise

    def _target_files(self, instance_path: str) -> list[Path]:
        tasks = self.write_plan.get_instance_tasks(instance_path)
        seen = set()
        files = []
        for task in tasks.values():
            rel_file = Path(task["fileName"])
            key = rel_file.as_posix()
            if key in seen:
                continue
            seen.add(key)
            files.append(rel_file)
        return files


class InputRestoreSnapshot:
    def __init__(self, instance_root: Path, backup_dir: Path, files: list[Path]):
        self.instanceRoot = instance_root
        self.backupDir = backup_dir
        self.files = files
        self._cleaned = False

    def restore(self) -> None:
        try:
            for rel_file in self.files:
                source = self.backupDir / rel_file
                if not source.exists():
                    continue
                target = self.instanceRoot / rel_file
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
        finally:
            self.cleanup()

    def cleanup(self) -> None:
        if self._cleaned:
            return
        shutil.rmtree(self.backupDir, ignore_errors=True)
        self._cleaned = True
