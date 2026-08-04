using System.Runtime.InteropServices;

namespace Billing;

// Managed wrapper over the native parser in native/parse.cpp (built as parser.dll).
// A returned length is sometimes wrong; unclear whether the bug is in the managed
// marshalling or inside the native parse_value.
public static class NativeParser
{
    [DllImport("parser", EntryPoint = "parse_value")]
    private static extern nint parse_value(string record, out int outLen);

    public static (string value, int length) Parse(string record)
    {
        nint ptr = parse_value(record, out int len);
        string value = Marshal.PtrToStringAnsi(ptr) ?? "";
        return (value, len);
    }
}
