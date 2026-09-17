"""vmem_server lifecycle. Started as the user (detached via setsid), stopped with
sudo pkill — the invocation proven out in the old phase1.sh, isolated here so the
runner doesn't carry it.
"""
import os
import subprocess
import time
from pathlib import Path


def _server_alive():
    return subprocess.run(["pgrep", "-x", "vmem_server"],
                          stdout=subprocess.DEVNULL).returncode == 0


class Server:
    def __init__(self, machine):
        self.m = machine
        self.repo = Path(machine["vmem_repo"])
        self.socket = self.repo / ".socket"      # app references this absolutely

    def start(self, dram_vpages, pmem_vpages, log_path):
        """Launch a server with exactly this many vpages per pool; block until it
        prints 'waiting for client' (or raise)."""
        self.stop()
        self._check_hugepages(dram_vpages, pmem_vpages)
        env = dict(os.environ,
                   VMEM_SOCKET_NAME=".socket",
                   VMEM_DRAM_PAGES=str(dram_vpages),
                   VMEM_PMEM_PAGES=str(pmem_vpages))
        cmd = f"cd '{self.repo}' && exec ./bin/vmem_server {self.m['server_flags']}"
        with open(log_path, "w") as log:
            subprocess.run(["setsid", "--fork", "bash", "-c", cmd], env=env,
                           stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
        for _ in range(240):
            txt = Path(log_path).read_text(errors="ignore") if Path(log_path).exists() else ""
            if "waiting for client" in txt:
                return
            if not _server_alive():
                raise RuntimeError(f"vmem_server died on startup (see {log_path})")
            time.sleep(1)
        raise RuntimeError(f"vmem_server not ready after 240s (see {log_path})")

    def _check_hugepages(self, dram_vpages, pmem_vpages):
        """Fail before starting if a node lacks free 2 MB hugepages for its pool: the
        caps in machine.yaml are only true while the sysfs setting they describe is,
        and that setting does not survive a reboot."""
        for node, want in ((self.m["dram_node"], dram_vpages), (self.m["pmem_node"], pmem_vpages)):
            f = Path(f"/sys/devices/system/node/node{node}/hugepages/hugepages-2048kB/free_hugepages")
            free = int(f.read_text())
            if free < want:
                raise RuntimeError(
                    f"node {node} has {free} free 2 MB hugepages but the pool needs {want} — "
                    f"reset nr_hugepages (see machine.yaml) or check for a leftover vmem_server")

    def stop(self):
        subprocess.run(["sudo", "pkill", "-9", "-x", "vmem_server"],
                       stderr=subprocess.DEVNULL)
        time.sleep(2)
