import queue
import shutil
import threading
from datetime import datetime
from pathlib import Path


class Workspace:
    def __init__(self, cfg, cfg_path: str):
        self.cfg = cfg
        self.cfgPath = cfg_path
        self.runPath = self._create_run_path()
        self.runQueue = queue.Queue()
        self.backupPath = self.runPath / "backup"
        self._cleanup_lock = threading.Lock()
        self._cleanup_done = False

        self._create_instances()
        self._backup_inputs()

    def _create_run_path(self) -> Path:
        now = datetime.now()
        base_time_str = now.strftime("%m%d_%H%M%S")
        run_path = Path(self.cfg.basic.workPath) / "tempRun" / base_time_str
        counter = 0
        while run_path.exists():
            micro_str = f"{now.microsecond + counter:06d}"
            run_path = Path(self.cfg.basic.workPath) / "tempRun" / f"{base_time_str}_{micro_str}"
            counter += 1
        run_path.mkdir(parents=True, exist_ok=True)
        return run_path

    def _create_instances(self) -> None:
        for i in range(self.cfg.basic.parallel):
            path = self.runPath / f"instance_{i}"
            shutil.copytree(self.cfg.basic.projectPath, path)
            self.runQueue.put(str(path))

    def _backup_inputs(self) -> None:
        self.backupPath.mkdir(parents=True, exist_ok=True)
        shutil.copy(self.cfgPath, self.backupPath)

        cfg_file = Path(self.cfgPath).resolve()
        resolved_path = cfg_file.parent / (cfg_file.stem + "_general.yaml")
        if resolved_path.exists():
            shutil.copy(resolved_path, self.backupPath)

        for series in self.cfg.series:
            if series.obs:
                obs_src = Path(series.obs.spec.file)
                if obs_src.exists():
                    shutil.copy(obs_src, self.backupPath)

    def acquire_instance(self) -> str:
        return self.runQueue.get()

    def release_instance(self, path: str) -> None:
        self.runQueue.put(path)

    def cleanup_instances(self) -> None:
        with self._cleanup_lock:
            if self._cleanup_done:
                return
            failed = []
            try:
                for name in self.runPath.iterdir():
                    if not name.is_dir():
                        continue
                    if name.name == "backup":
                        continue
                    if name.name.startswith("instance_"):
                        try:
                            shutil.rmtree(name)
                        except Exception as e:
                            failed.append((str(name), str(e)))
            finally:
                self._cleanup_done = True
            if failed:
                print("[Workspace.cleanup] Failed to remove some instance folders:")
                for path, err in failed:
                    print(f"  - {path}: {err}")
                print("Please remove them manually if needed.")
