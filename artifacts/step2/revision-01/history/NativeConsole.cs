// Test harness only: direct hidden-console launch and Ctrl+C. No Job Object.
using System;
using System.ComponentModel;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;

public static class SpectrumTestConsole
{
    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    private struct STARTUPINFO
    {
        public int cb;
        public string lpReserved, lpDesktop, lpTitle;
        public int dwX, dwY, dwXSize, dwYSize, dwXCountChars, dwYCountChars;
        public int dwFillAttribute, dwFlags;
        public short wShowWindow, cbReserved2;
        public IntPtr lpReserved2, hStdInput, hStdOutput, hStdError;
    }
    [StructLayout(LayoutKind.Sequential)]
    private struct PROCESS_INFORMATION
    {
        public IntPtr hProcess, hThread;
        public int dwProcessId, dwThreadId;
    }
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern bool CreateProcessW(string application, StringBuilder command,
        IntPtr processAttributes, IntPtr threadAttributes, bool inheritHandles,
        uint flags, IntPtr environment, string directory,
        ref STARTUPINFO startup, out PROCESS_INFORMATION process);
    [DllImport("kernel32.dll")] private static extern bool CloseHandle(IntPtr handle);
    [DllImport("kernel32.dll", SetLastError = true)] private static extern bool FreeConsole();
    [DllImport("kernel32.dll", SetLastError = true)] private static extern bool AttachConsole(uint pid);
    [DllImport("kernel32.dll", SetLastError = true)] private static extern bool SetConsoleCtrlHandler(IntPtr handler, bool add);
    [DllImport("kernel32.dll", SetLastError = true)] private static extern bool GenerateConsoleCtrlEvent(uint signal, uint group);

    public static int Start(string executable, string directory)
    {
        var startup = new STARTUPINFO { cb = Marshal.SizeOf<STARTUPINFO>(), dwFlags = 1, wShowWindow = 0 };
        PROCESS_INFORMATION process;
        // CREATE_NEW_CONSOLE; SW_HIDE. The exe runs directly, with no command shell.
        if (!CreateProcessW(executable, new StringBuilder("\"" + executable + "\""),
            IntPtr.Zero, IntPtr.Zero, false, 0x10, IntPtr.Zero, directory,
            ref startup, out process)) throw new Win32Exception(Marshal.GetLastWin32Error());
        CloseHandle(process.hThread);
        CloseHandle(process.hProcess);
        return process.dwProcessId;
    }

    public static void SendCtrlC(uint pid)
    {
        // Called in a separate, short-lived PowerShell helper, not the test driver.
        FreeConsole();
        if (!AttachConsole(pid)) throw new Win32Exception(Marshal.GetLastWin32Error());
        try
        {
            if (!SetConsoleCtrlHandler(IntPtr.Zero, true)) throw new Win32Exception(Marshal.GetLastWin32Error());
            if (!GenerateConsoleCtrlEvent(0, 0)) throw new Win32Exception(Marshal.GetLastWin32Error());
            Thread.Sleep(300);
        }
        finally { FreeConsole(); }
    }
}
