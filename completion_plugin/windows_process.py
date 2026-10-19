"""Windows-only bounded runner for trusted, fixed executable/argument lists.

A Job Object contains the suspended process before any application code runs.
This is process-tree cleanup, not a security sandbox for hostile programs.
"""
import math
import os
import subprocess
import tempfile
import time

OUTPUT_LIMIT = 8 * 1024 * 1024
POLL_SECONDS = 0.02


class OutputLimitExceeded(RuntimeError):
    """The output watchdog stopped a command exceeding its capture budget."""


def _excerpt(stream):
    stream.seek(0, 2)
    size = stream.tell()
    stream.seek(0)
    if size <= 19000:
        data = stream.read()
    else:
        head = stream.read(9000)
        stream.seek(-9000, 2)
        data = head + b'\n[output truncated]\n' + stream.read(9000)
    return data.decode('utf-8', errors='replace')


def run_windows(command, root, timeout=20):
    """Run a fixed argv, returning CompletedProcess with bounded text excerpts.

    timeout is positive and at most 20 seconds. TimeoutExpired and
    OutputLimitExceeded propagate after containment cleanup. Fail closed if job
    assignment is unavailable (including incompatible host Job Object policy).
    """
    if os.name != 'nt':
        raise OSError('Windows Job Object runner requires native Windows')
    if isinstance(command, (str, bytes)) or not command:
        raise ValueError('command must be a nonempty fixed argument list')
    command = list(command)
    if any(not isinstance(arg, str) or '\0' in arg for arg in command):
        raise ValueError('command arguments must be NUL-free strings')
    if not os.path.isabs(command[0]):
        raise ValueError('executable must be an absolute path')
    if not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or not 0 < timeout <= 20:
        raise ValueError('timeout must be positive and at most 20 seconds')
    return _run_native(command, os.fspath(root), timeout)


def _run_native(command, root, timeout):
    import ctypes as c
    import msvcrt
    from ctypes import wintypes as w

    k = c.WinDLL('kernel32', use_last_error=True)
    SIZE_T = c.c_size_t
    class IO_COUNTERS(c.Structure):
        _fields_ = [(name, c.c_ulonglong) for name in (
            'ReadOperationCount', 'WriteOperationCount', 'OtherOperationCount',
            'ReadTransferCount', 'WriteTransferCount', 'OtherTransferCount')]
    class BASIC_LIMIT(c.Structure):
        _fields_ = [('PerProcessUserTimeLimit', c.c_longlong), ('PerJobUserTimeLimit', c.c_longlong),
                    ('LimitFlags', w.DWORD), ('MinimumWorkingSetSize', SIZE_T),
                    ('MaximumWorkingSetSize', SIZE_T), ('ActiveProcessLimit', w.DWORD),
                    ('Affinity', SIZE_T), ('PriorityClass', w.DWORD), ('SchedulingClass', w.DWORD)]
    class EXTENDED_LIMIT(c.Structure):
        _fields_ = [('BasicLimitInformation', BASIC_LIMIT), ('IoInfo', IO_COUNTERS),
                    ('ProcessMemoryLimit', SIZE_T), ('JobMemoryLimit', SIZE_T),
                    ('PeakProcessMemoryUsed', SIZE_T), ('PeakJobMemoryUsed', SIZE_T)]
    class ACCOUNTING(c.Structure):
        _fields_ = [('TotalUserTime', c.c_longlong), ('TotalKernelTime', c.c_longlong),
                    ('ThisPeriodTotalUserTime', c.c_longlong), ('ThisPeriodTotalKernelTime', c.c_longlong),
                    ('TotalPageFaultCount', w.DWORD), ('TotalProcesses', w.DWORD),
                    ('ActiveProcesses', w.DWORD), ('TotalTerminatedProcesses', w.DWORD)]
    class STARTUPINFO(c.Structure):
        _fields_ = [('cb', w.DWORD), ('lpReserved', w.LPWSTR), ('lpDesktop', w.LPWSTR),
                    ('lpTitle', w.LPWSTR), ('dwX', w.DWORD), ('dwY', w.DWORD),
                    ('dwXSize', w.DWORD), ('dwYSize', w.DWORD), ('dwXCountChars', w.DWORD),
                    ('dwYCountChars', w.DWORD), ('dwFillAttribute', w.DWORD), ('dwFlags', w.DWORD),
                    ('wShowWindow', w.WORD), ('cbReserved2', w.WORD), ('lpReserved2', c.POINTER(c.c_byte)),
                    ('hStdInput', w.HANDLE), ('hStdOutput', w.HANDLE), ('hStdError', w.HANDLE)]
    class STARTUPINFOEX(c.Structure):
        _fields_ = [('StartupInfo', STARTUPINFO), ('lpAttributeList', c.c_void_p)]
    class PROCESS_INFORMATION(c.Structure):
        _fields_ = [('hProcess', w.HANDLE), ('hThread', w.HANDLE), ('dwProcessId', w.DWORD), ('dwThreadId', w.DWORD)]

    def bind(name, args, result=w.BOOL):
        fn = getattr(k, name)
        fn.argtypes, fn.restype = args, result
        return fn
    create_job = bind('CreateJobObjectW', [c.c_void_p, w.LPCWSTR], w.HANDLE)
    set_job = bind('SetInformationJobObject', [w.HANDLE, c.c_int, c.c_void_p, w.DWORD])
    assign_job = bind('AssignProcessToJobObject', [w.HANDLE, w.HANDLE])
    terminate_job = bind('TerminateJobObject', [w.HANDLE, w.UINT])
    query_job = bind('QueryInformationJobObject', [w.HANDLE, c.c_int, c.c_void_p, w.DWORD, c.c_void_p])
    close = bind('CloseHandle', [w.HANDLE])
    init_attrs = bind('InitializeProcThreadAttributeList', [c.c_void_p, w.DWORD, w.DWORD, c.POINTER(SIZE_T)])
    update_attrs = bind('UpdateProcThreadAttribute', [c.c_void_p, w.DWORD, SIZE_T, c.c_void_p, SIZE_T, c.c_void_p, c.c_void_p])
    delete_attrs = bind('DeleteProcThreadAttributeList', [c.c_void_p], None)
    create_process = bind('CreateProcessW', [w.LPCWSTR, w.LPWSTR, c.c_void_p, c.c_void_p,
                                          w.BOOL, w.DWORD, c.c_void_p, w.LPCWSTR,
                                          c.POINTER(STARTUPINFOEX), c.POINTER(PROCESS_INFORMATION)])
    resume = bind('ResumeThread', [w.HANDLE], w.DWORD)
    wait = bind('WaitForSingleObject', [w.HANDLE, w.DWORD], w.DWORD)
    exit_code = bind('GetExitCodeProcess', [w.HANDLE, c.POINTER(w.DWORD)])
    terminate_process = bind('TerminateProcess', [w.HANDLE, w.UINT])
    def check(ok):
        if not ok:
            raise c.WinError(c.get_last_error())
        return ok

    with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err, open(os.devnull, 'rb') as inp:
        job = check(create_job(None, None))
        pi = PROCESS_INFORMATION()
        attrs = None
        attrs_initialized = False
        assigned = False
        try:
            limits = EXTENDED_LIMIT()
            limits.BasicLimitInformation.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            check(set_job(job, 9, c.byref(limits), c.sizeof(limits)))
            handles = (w.HANDLE * 3)(*[msvcrt.get_osfhandle(s.fileno()) for s in (inp, out, err)])
            for handle in handles:
                os.set_handle_inheritable(handle, True)
            size = SIZE_T()
            init_attrs(None, 1, 0, c.byref(size))
            attrs = c.create_string_buffer(size.value)
            check(init_attrs(attrs, 1, 0, c.byref(size)))
            attrs_initialized = True
            check(update_attrs(attrs, 0, 0x20002, handles, c.sizeof(handles), None, None))
            si = STARTUPINFOEX()
            si.StartupInfo.cb = c.sizeof(si)
            si.StartupInfo.dwFlags = 0x100  # STARTF_USESTDHANDLES
            si.StartupInfo.hStdInput, si.StartupInfo.hStdOutput, si.StartupInfo.hStdError = handles
            si.lpAttributeList = c.cast(attrs, c.c_void_p)
            system_root = os.environ.get('SystemRoot', r'C:\Windows')
            env = {'SystemRoot': system_root, 'WINDIR': system_root,
                   'PATH': os.path.join(system_root, 'System32'),
                   'PYTHONUTF8': '1', 'PYTHONDONTWRITEBYTECODE': '1'}
            env_buffer = c.create_unicode_buffer('\0'.join(f'{key}={value}' for key, value in sorted(env.items())) + '\0\0')
            cmd_buffer = c.create_unicode_buffer(subprocess.list2cmdline(command))
            # No breakaway: failure to join our job leaves the process suspended.
            flags = 0x4 | 0x400 | 0x80000 | 0x08000000
            try:
                check(create_process(command[0], cmd_buffer, None, None, True, flags,
                                     env_buffer, root, c.byref(si), c.byref(pi)))
            finally:
                # Limit the inheritable window to process creation, not its lifetime.
                for handle in handles:
                    os.set_handle_inheritable(handle, False)
            check(assign_job(job, pi.hProcess))
            assigned = True
            if resume(pi.hThread) == 0xFFFFFFFF:
                raise c.WinError(c.get_last_error())
            deadline = time.monotonic() + timeout
            while True:
                if os.fstat(out.fileno()).st_size + os.fstat(err.fileno()).st_size > OUTPUT_LIMIT:
                    raise OutputLimitExceeded('Command exceeded 8 MiB output watchdog budget')
                status = wait(pi.hProcess, 0)
                if status == 0:
                    break
                if status != 0x102:
                    raise c.WinError(c.get_last_error())
                if time.monotonic() >= deadline:
                    raise subprocess.TimeoutExpired(command, timeout)
                time.sleep(min(POLL_SECONDS, max(0, deadline - time.monotonic())))
            code = w.DWORD()
            check(exit_code(pi.hProcess, c.byref(code)))
        finally:
            try:
                if pi.hProcess:
                    if assigned:
                        check(terminate_job(job, 1))
                    else:
                        check(terminate_process(pi.hProcess, 1))
                    # Wait for descendants too, so they cannot retain capture files.
                    cleanup_deadline = time.monotonic() + 5
                    while True:
                        accounting = ACCOUNTING()
                        if assigned:
                            check(query_job(job, 1, c.byref(accounting), c.sizeof(accounting), None))
                        if wait(pi.hProcess, 0) == 0 and (not assigned or accounting.ActiveProcesses == 0):
                            break
                        if time.monotonic() >= cleanup_deadline:
                            raise OSError('Windows process-tree cleanup did not finish within 5 seconds')
                        time.sleep(POLL_SECONDS)
            finally:
                if pi.hThread:
                    close(pi.hThread)
                if pi.hProcess:
                    close(pi.hProcess)
                close(job)  # kill-on-close remains a backstop even if cleanup failed
                if attrs_initialized:
                    delete_attrs(attrs)
                for stream in (inp, out, err):
                    os.set_handle_inheritable(msvcrt.get_osfhandle(stream.fileno()), False)
        # Cover output written between the last watchdog sample and tree shutdown.
        if os.fstat(out.fileno()).st_size + os.fstat(err.fileno()).st_size > OUTPUT_LIMIT:
            raise OutputLimitExceeded('Command exceeded 8 MiB output watchdog budget')
        return subprocess.CompletedProcess(command, code.value, _excerpt(out), _excerpt(err))
