"""Windows Task Scheduler service manager."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Optional
import xml.etree.ElementTree as ET

from dgmt.service.base import ServiceInfo, ServiceManager, ServiceStatus
from dgmt.utils.logging import get_logger


class WindowsServiceManager(ServiceManager):
    """
    Service manager for Windows using Task Scheduler.

    Creates a scheduled task that runs at logon and restarts on failure.
    """

    TASK_XML_TEMPLATE = """\
<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>{description}</Description>
    <Author>{username}</Author>
  </RegistrationInfo>
  <Triggers>
    <LogonTrigger>
      <Enabled>true</Enabled>
      <UserId>{username}</UserId>
    </LogonTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <UserId>{username}</UserId>
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
    <IdleSettings>
      <StopOnIdleEnd>false</StopOnIdleEnd>
      <RestartOnIdle>false</RestartOnIdle>
    </IdleSettings>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>false</Hidden>
    <RunOnlyIfIdle>false</RunOnlyIfIdle>
    <WakeToRun>false</WakeToRun>
    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
    <Priority>7</Priority>
    <RestartOnFailure>
      <Interval>PT1M</Interval>
      <Count>3</Count>
    </RestartOnFailure>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>{python}</Command>
      <Arguments>-m dgmt run</Arguments>
      <WorkingDirectory>{working_dir}</WorkingDirectory>
    </Exec>
  </Actions>
</Task>
"""

    def __init__(self) -> None:
        self._logger = get_logger("dgmt.service")
        self._task_name = self.SERVICE_NAME

    @property
    def platform_name(self) -> str:
        return "windows"

    def _get_startupinfo(self) -> subprocess.STARTUPINFO:
        """Get STARTUPINFO to hide console windows."""
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0
        return startupinfo

    def _run_schtasks(self, *args: str) -> subprocess.CompletedProcess:
        """Run a schtasks command."""
        cmd = ["schtasks", *args]
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            startupinfo=self._get_startupinfo(),
            creationflags=subprocess.CREATE_NO_WINDOW,
        )

    def install(self, python_path: Optional[str] = None) -> bool:
        """Install dgmt as a Windows scheduled task."""
        python = python_path or sys.executable
        # Use pythonw.exe to avoid console window
        if python.endswith("python.exe"):
            pythonw = python.replace("python.exe", "pythonw.exe")
            if os.path.exists(pythonw):
                python = pythonw
        username = os.environ.get("USERNAME", "")
        working_dir = str(Path.home())

        # Create task XML
        task_xml = self.TASK_XML_TEMPLATE.format(
            description=self.SERVICE_DESCRIPTION,
            username=username,
            python=python,
            working_dir=working_dir,
        )

        # Write XML to temp file
        temp_dir = Path(os.environ.get("TEMP", "."))
        xml_file = temp_dir / f"{self._task_name}_task.xml"

        try:
            # Write with UTF-16 encoding (required by Task Scheduler)
            xml_file.write_text(task_xml, encoding="utf-16")
        except Exception as e:
            self._logger.error(f"Failed to write task XML: {e}")
            return False

        # Create the task
        result = self._run_schtasks(
            "/Create",
            "/TN", self._task_name,
            "/XML", str(xml_file),
            "/F",  # Force overwrite if exists
        )

        # Clean up temp file
        try:
            xml_file.unlink()
        except Exception:
            pass

        if result.returncode != 0:
            self._logger.error(f"Failed to create task: {result.stderr}")
            return False

        self._logger.info(f"Task '{self._task_name}' created successfully")
        return True

    def uninstall(self) -> bool:
        """Remove the Windows scheduled task."""
        # Stop the task first
        self.stop()

        result = self._run_schtasks("/Delete", "/TN", self._task_name, "/F")

        if result.returncode != 0:
            if "cannot find the file" in result.stderr.lower():
                self._logger.info("Task was not installed")
                return True
            self._logger.error(f"Failed to delete task: {result.stderr}")
            return False

        self._logger.info(f"Task '{self._task_name}' deleted")
        return True

    def start(self) -> bool:
        """Start the dgmt task."""
        result = self._run_schtasks("/Run", "/TN", self._task_name)

        if result.returncode != 0:
            self._logger.error(f"Failed to start task: {result.stderr}")
            return False

        self._logger.info(f"Task '{self._task_name}' started")
        return True

    def stop(self) -> bool:
        """Stop the dgmt task."""
        result = self._run_schtasks("/End", "/TN", self._task_name)

        if result.returncode != 0:
            # Task might not be running
            if "is not currently running" in result.stderr.lower():
                return True
            self._logger.error(f"Failed to stop task: {result.stderr}")
            return False

        self._logger.info(f"Task '{self._task_name}' stopped")
        return True

    def restart(self) -> bool:
        """Restart the dgmt task."""
        self.stop()
        return self.start()

    def status(self) -> ServiceInfo:
        """Get current task status."""
        result = self._run_schtasks(
            "/Query",
            "/TN", self._task_name,
            "/FO", "CSV",
            "/V",
        )

        if result.returncode != 0:
            if "cannot find" in result.stderr.lower():
                return ServiceInfo(
                    name=self._task_name,
                    status=ServiceStatus.NOT_INSTALLED,
                )
            return ServiceInfo(
                name=self._task_name,
                status=ServiceStatus.ERROR,
                error_message=result.stderr,
            )

        # Parse CSV output
        lines = result.stdout.strip().split("\n")
        if len(lines) < 2:
            return ServiceInfo(
                name=self._task_name,
                status=ServiceStatus.UNKNOWN,
            )

        # Parse header and data
        try:
            header = lines[0].strip('"').split('","')
            data = lines[1].strip('"').split('","')
            task_info = dict(zip(header, data))

            status_text = task_info.get("Status", "").lower()
            if status_text == "running":
                status = ServiceStatus.RUNNING
            elif status_text in ("ready", "disabled"):
                status = ServiceStatus.STOPPED
            else:
                status = ServiceStatus.UNKNOWN

            return ServiceInfo(
                name=self._task_name,
                status=status,
                description=task_info.get("Task To Run"),
            )
        except Exception:
            return ServiceInfo(
                name=self._task_name,
                status=ServiceStatus.UNKNOWN,
            )

    def is_installed(self) -> bool:
        """Check if the task is installed."""
        result = self._run_schtasks("/Query", "/TN", self._task_name)
        return result.returncode == 0

    def enable(self) -> bool:
        """Enable the task."""
        result = self._run_schtasks("/Change", "/TN", self._task_name, "/ENABLE")
        return result.returncode == 0

    def disable(self) -> bool:
        """Disable the task."""
        result = self._run_schtasks("/Change", "/TN", self._task_name, "/DISABLE")
        return result.returncode == 0
