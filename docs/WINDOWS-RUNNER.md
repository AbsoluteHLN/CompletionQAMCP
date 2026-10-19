# Windows contained process runner

`completion_plugin.windows_process.run_windows(command, root, timeout=20)`
accepts a fixed argument list whose first element is an absolute executable path.
It returns a `subprocess.CompletedProcess` with text stdout/stderr excerpts.
The caller must supply only the approved project-check command; this module does
not decide whether an arbitrary executable or project is trustworthy.

## Lifecycle

- Imports safely on Linux, but execution fails explicitly off native Windows.
- Creates a Job Object with `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`.
- Creates the process with `CREATE_SUSPENDED`, with no breakaway flags.
- Assigns the process to the Job Object before `ResumeThread`. Assignment failure
  terminates the still-suspended process and fails closed. Existing host Job
  Object restrictions can therefore prevent execution rather than weaken it.
- Uses `STARTUPINFOEX` with an explicit three-handle inheritance list: NUL stdin
  and temporary stdout/stderr files. No shell or executable PATH lookup is used. Parent handles become non-inheritable immediately after process creation. Concurrent unrelated broad-handle-inheritance process creation can still race that brief window; a host must coordinate such launches.
- Gives the process only SystemRoot, WINDIR, a System32 PATH, PYTHONUTF8, and
  PYTHONDONTWRITEBYTECODE. It does not pass user environment secrets.
- Allows at most 20 seconds execution (a shorter positive timeout is accepted).
- Polls process status and combined capture size every 20 ms. Output above 8 MiB
  raises `OutputLimitExceeded`. This is a watchdog threshold, not an exact disk
  quota: output can overshoot between polls. Returned excerpts are at most 19,000
  source bytes per stream, or 9,000-byte head/tail with a truncation marker.
- On success, nonzero exit, timeout, or error, terminates the contained job,
  waits up to five additional seconds for active descendants to disappear, and
  closes process, thread, job, attribute-list, and file resources. Failure before
  assignment terminates the suspended process directly. Job close is an extra
  kill backstop if explicit cleanup fails. Cleanup failure is reported.

The Job Object is process containment/cleanup for trusted checks, not a security
sandbox. It does not restrict network/file access, prevent all OS-service-mediated
execution, impose CPU/memory quotas, or remove the need for user authorization.
No native Windows success is claimed from Linux test runs.

## Validation

Run from the project root on native Windows:

    python -m unittest discover -s tests -p test_windows_process.py -v

Native tests cover stdout/stderr, nonzero exit, minimal environment, timeout,
output watchdog, process creation failure, and descendant cleanup after normal
exit, timeout, and output error. Linux runs execute only the portable contract
checks and explicitly skip the native lifecycle tests. A Windows release/trial
must retain the actual native test output separately; skipped tests are not
native validation evidence.

## References

- https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects
- https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-createprocessw
- https://learn.microsoft.com/en-us/windows/win32/api/jobapi2/nf-jobapi2-assignprocesstojobobject
- https://learn.microsoft.com/en-us/windows/win32/api/jobapi2/nf-jobapi2-setinformationjobobject
- https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-updateprocthreadattribute
