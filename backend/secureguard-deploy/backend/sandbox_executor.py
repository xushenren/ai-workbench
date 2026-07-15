"""backend.sandbox_executor — 代码执行器（问题2）。

⚠️⚠️ 安全红线（务必读）⚠️⚠️
执行 AI 生成的代码是本系统最危险的操作。本文件的子进程实现（SubprocessExecutor）
**不是真正的隔离**——它能挡住"跑太久/吃太多内存/fork 炸弹/写大文件"，但**挡不住**
读取服务器文件、外传数据（若网络未禁）、或利用内核漏洞逃逸。

生产环境**必须**用容器隔离（服务器已装 Docker 29.1.3、用户命名空间已开）：
  DockerExecutor（下方协议占位）应以 `--network=none --read-only --memory --pids-limit
  --cap-drop=ALL --security-opt=no-new-privileges` 在一次性容器里跑。
子进程实现仅供"沙箱未部署时的降级"与离线测试，**不可作为对不可信代码的最终防线**。

接口契约（两种实现都遵守）：
    execute(code, language="python") -> {
        available: bool, exit_code: int|None, stdout: str, stderr: str,
        duration_ms: int, timed_out: bool, error: str
    }
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
from typing import Any, Dict, Optional


class SandboxExecutor:
    """执行器基类 + 工厂。默认给子进程参考实现；available=False 时优雅降级。"""

    def __init__(self, available: bool = True, timeout: int = 30,
                 mem_mb: int = 256, backend: str = "subprocess",
                 image: str = "python:3.12-slim") -> None:
        self.available = available
        self.timeout = timeout
        self.mem_mb = mem_mb
        self.backend = backend
        self.image = image

    def execute(self, code: str, language: str = "python") -> Dict[str, Any]:
        if not self.available:
            # 沙箱未部署：优雅降级，绝不假装跑过（与 output_contract 的 fail-closed 一致）
            return {"available": False, "exit_code": None, "stdout": "", "stderr": "",
                    "duration_ms": 0, "timed_out": False, "error": "sandbox_not_available"}
        if language != "python":
            return {"available": True, "exit_code": None, "stdout": "", "stderr": "",
                    "duration_ms": 0, "timed_out": False, "error": f"unsupported_language:{language}"}
        if self.backend == "docker":
            return self._run_docker(code)
        return self._run_subprocess(code)

    # ---------- 子进程参考实现（⚠️ 非真隔离） ----------
    def _run_subprocess(self, code: str) -> Dict[str, Any]:
        import signal
        t0 = time.time()
        path = None
        try:
            with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as f:
                f.write(code)
                path = f.name
            r = subprocess.run(
                [sys.executable, "-I", path],            # -I：隔离模式，忽略环境/用户 site
                capture_output=True, text=True, timeout=self.timeout,
                preexec_fn=self._limits if os.name == "posix" else None,
                env={"PATH": "/usr/bin:/bin", "PYTHONNOUSERSITE": "1"},  # 最小环境
                cwd=tempfile.gettempdir(),
            )
            # 被信号杀死（返回码为负）：SIGXCPU/SIGKILL 多为资源超限，归为超时类，跨平台一致
            if r.returncode is not None and r.returncode < 0:
                sig = -r.returncode
                resource_kill = sig in (getattr(signal, "SIGXCPU", 24), signal.SIGKILL)
                return {"available": True, "exit_code": r.returncode,
                        "stdout": r.stdout[:10000], "stderr": r.stderr[:4000],
                        "duration_ms": int((time.time() - t0) * 1000),
                        "timed_out": resource_kill,
                        "error": f"timeout_killed_sig{sig}" if resource_kill else f"killed_sig{sig}"}
            return {"available": True, "exit_code": r.returncode,
                    "stdout": r.stdout[:10000], "stderr": r.stderr[:4000],
                    "duration_ms": int((time.time() - t0) * 1000),
                    "timed_out": False, "error": ""}
        except subprocess.TimeoutExpired:
            return {"available": True, "exit_code": None, "stdout": "", "stderr": "",
                    "duration_ms": int((time.time() - t0) * 1000),
                    "timed_out": True, "error": f"timeout_{self.timeout}s"}
        except Exception as e:  # pragma: no cover
            return {"available": True, "exit_code": None, "stdout": "", "stderr": "",
                    "duration_ms": int((time.time() - t0) * 1000),
                    "timed_out": False, "error": f"exec_error:{e}"}
        finally:
            if path and os.path.exists(path):
                try:
                    os.unlink(path)
                except OSError:
                    pass

    def _limits(self) -> None:  # pragma: no cover - 子进程内执行
        """子进程资源限制：CPU、内存、禁 fork、限文件大小。POSIX only。

        RLIMIT_CPU 设为墙钟超时+5：墙钟超时(subprocess timeout)当主闸先触发，
        CPU 限制只作"逃过墙钟的 CPU 暴走"的兜底——避免两个超时同值打架（曾致
        死循环在不同平台一会儿被墙钟杀、一会儿被 CPU 限杀，timed_out 结果不稳定）。
        """
        import resource
        resource.setrlimit(resource.RLIMIT_CPU, (self.timeout + 5, self.timeout + 5))
        m = self.mem_mb * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (m, m))
        resource.setrlimit(resource.RLIMIT_NPROC, (0, 0))          # 防 fork 炸弹
        resource.setrlimit(resource.RLIMIT_FSIZE, (5 * 1024 * 1024, 5 * 1024 * 1024))  # 限写 5MB

    # ---------- Docker 隔离实现（🔴 真隔离，需服务器有 Docker；本沙箱无法验证） ----------
    def _run_docker(self, code: str) -> Dict[str, Any]:  # pragma: no cover - 需 Docker 环境
        """一次性容器隔离执行。安全参数齐全，但**必须在你服务器上实测逃逸防护**。

        隔离要点：--network=none 禁网（防外传）、--read-only 只读根（防篡改）、
        --memory/--pids-limit 限资源（防 OOM/fork 炸弹）、--cap-drop=ALL 丢所有能力、
        --security-opt=no-new-privileges 禁提权、非 root 用户、tmpfs 限大小。
        """
        import json
        t0 = time.time()
        path = None
        try:
            with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as f:
                f.write(code)
                path = f.name
            os.chmod(path, 0o644)  # nobody(65534) 在容器内需要读权限
            cmd = [
                "docker", "run", "--rm",
                "--network=none",                      # 禁网：防数据外传
                "--read-only",                         # 根文件系统只读
                "--tmpfs", "/tmp:rw,size=16m,noexec",  # 仅 /tmp 可写且禁执行
                f"--memory={self.mem_mb}m", "--memory-swap", f"{self.mem_mb}m",
                "--pids-limit=64",                     # 防 fork 炸弹
                "--cpus=1",
                "--cap-drop=ALL",                      # 丢所有 Linux capabilities
                "--security-opt=no-new-privileges",
                "--user", "65534:65534",               # nobody，非 root
                "-v", f"{path}:/code.py:ro",
                self.image, "python", "-I", "/code.py",
            ]
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=self.timeout + 5)
            return {"available": True, "exit_code": r.returncode,
                    "stdout": r.stdout[:10000], "stderr": r.stderr[:4000],
                    "duration_ms": int((time.time() - t0) * 1000),
                    "timed_out": False, "error": "" if r.returncode == 0 else "nonzero_exit",
                    "backend": "docker"}
        except subprocess.TimeoutExpired:
            return {"available": True, "exit_code": None, "stdout": "", "stderr": "",
                    "duration_ms": int((time.time() - t0) * 1000),
                    "timed_out": True, "error": f"timeout_{self.timeout}s", "backend": "docker"}
        except FileNotFoundError:
            return {"available": False, "exit_code": None, "stdout": "", "stderr": "",
                    "duration_ms": 0, "timed_out": False,
                    "error": "docker_not_found（服务器未装 Docker 或不在 PATH）", "backend": "docker"}
        except Exception as e:
            return {"available": True, "exit_code": None, "stdout": "", "stderr": "",
                    "duration_ms": int((time.time() - t0) * 1000),
                    "timed_out": False, "error": f"docker_error:{e}", "backend": "docker"}
        finally:
            if path and os.path.exists(path):
                try:
                    os.unlink(path)
                except OSError:
                    pass


def build_executor() -> SandboxExecutor:
    """按环境变量构造。SANDBOX_ENABLED=0 → 降级；SANDBOX_BACKEND=docker → 真隔离（你接）。

    生产建议：SANDBOX_BACKEND=docker + SANDBOX_IMAGE=python:3.12-slim（先 docker pull）。
    子进程版仅作降级/离线测，不可作不可信代码的最终防线。
    """
    enabled = os.environ.get("SANDBOX_ENABLED", "1") != "0"
    backend = os.environ.get("SANDBOX_BACKEND", "subprocess")
    timeout = int(os.environ.get("SANDBOX_TIMEOUT", "30"))
    image = os.environ.get("SANDBOX_IMAGE", "python:3.12-slim")
    return SandboxExecutor(available=enabled, timeout=timeout, backend=backend, image=image)
