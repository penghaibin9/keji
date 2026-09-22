"""Secure no-follow file opens on POSIX and Windows.

Windows uses OPEN_REPARSE_POINT, rejects reparse/directory handles and verifies
the final handle path. It does not emulate O_NOFOLLOW by dropping the flag.
"""
from pathlib import Path
import os, stat, errno

def _reject_reparse_parents(path):
    for parent in path.parents:
        info=parent.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info,'st_file_attributes',0)&0x400:
            raise OSError(errno.ELOOP,'Reparse parent forbidden')

def open_nofollow(path,flags,mode=0o600):
    path=Path(os.path.abspath(path))
    if os.name!='nt':
        return os.open(path,flags|os.O_NOFOLLOW,mode)
    import ctypes,msvcrt
    from ctypes import wintypes
    _reject_reparse_parents(path)
    create=bool(flags&os.O_CREAT)
    if create and not flags&os.O_EXCL:
        raise ValueError('Secure writes require exclusive creation')
    if flags&os.O_TRUNC or flags&os.O_APPEND:
        raise ValueError('Secure writes do not truncate or append')
    write=bool(flags&(os.O_WRONLY|os.O_RDWR))
    access=0x40000000 if write else 0x80000000
    if flags&os.O_RDWR:access|=0x80000000
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    class FileInfo(ctypes.Structure):
        _fields_=[('attributes',wintypes.DWORD),('created',wintypes.FILETIME),
                  ('accessed',wintypes.FILETIME),('written',wintypes.FILETIME),
                  ('volume',wintypes.DWORD),('size_high',wintypes.DWORD),
                  ('size_low',wintypes.DWORD),('links',wintypes.DWORD),
                  ('index_high',wintypes.DWORD),('index_low',wintypes.DWORD)]
    kernel.CreateFileW.argtypes=[wintypes.LPCWSTR,wintypes.DWORD,wintypes.DWORD,
                                wintypes.LPVOID,wintypes.DWORD,wintypes.DWORD,wintypes.HANDLE]
    kernel.CreateFileW.restype=wintypes.HANDLE
    kernel.GetFileInformationByHandle.argtypes=[wintypes.HANDLE,ctypes.POINTER(FileInfo)]
    kernel.GetFileInformationByHandle.restype=wintypes.BOOL
    kernel.GetFinalPathNameByHandleW.argtypes=[wintypes.HANDLE,wintypes.LPWSTR,wintypes.DWORD,wintypes.DWORD]
    kernel.GetFinalPathNameByHandleW.restype=wintypes.DWORD
    kernel.CloseHandle.argtypes=[wintypes.HANDLE]
    kernel.CloseHandle.restype=wintypes.BOOL
    # Share read only: no simultaneous writer or deletion/replacement during read.
    handle=kernel.CreateFileW(str(path),access,1,None,1 if create else 3,0x00200000|0x80,None)
    if handle==ctypes.c_void_p(-1).value:raise ctypes.WinError(ctypes.get_last_error())
    try:
        info=FileInfo()
        if not kernel.GetFileInformationByHandle(handle,ctypes.byref(info)):
            raise ctypes.WinError(ctypes.get_last_error())
        if info.attributes&(0x400|0x10):
            raise OSError(errno.ELOOP,'Reparse or directory file forbidden')
        buffer=ctypes.create_unicode_buffer(32768)
        size=kernel.GetFinalPathNameByHandleW(handle,buffer,len(buffer),0)
        if not size or size>=len(buffer):raise OSError(errno.EIO,'Cannot verify file handle path')
        actual=buffer.value
        if actual.startswith('\\\\?\\UNC\\'):actual='\\\\'+actual[8:]
        elif actual.startswith('\\\\?\\'):actual=actual[4:]
        if os.path.normcase(os.path.abspath(actual))!=os.path.normcase(str(path)):
            raise OSError(errno.ELOOP,'File handle escaped expected path')
        fd=msvcrt.open_osfhandle(handle,(os.O_RDWR if flags&os.O_RDWR else os.O_WRONLY if write else os.O_RDONLY)|os.O_BINARY)
        handle=None
        return fd
    finally:
        if handle is not None:kernel.CloseHandle(handle)

