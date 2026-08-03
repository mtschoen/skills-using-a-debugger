using System.Runtime.InteropServices;
using System.Text;

namespace MockRepo;

// P/Invokes into native/parse.cpp, built as parser.dll (or libparser.so /
// libparser.dylib on other platforms), to reuse the native record parser
// from managed code.
internal static class NativeParser
{
    [DllImport("parser", EntryPoint = "parse_value", CallingConvention = CallingConvention.Cdecl)]
    private static extern int ParseValueNative(
        byte[] rec,
        System.UIntPtr recLen,
        byte[] outBuf,
        out System.UIntPtr outLen);

    public static string Parse(byte[] record)
    {
        var outBuf = new byte[record.Length];
        int status = ParseValueNative(record, (System.UIntPtr)record.Length, outBuf, out var outLen);
        if (status != 0)
        {
            return null;
        }
        return Encoding.UTF8.GetString(outBuf, 0, (int)outLen);
    }
}
