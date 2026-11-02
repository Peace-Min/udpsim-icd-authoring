using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Text;
using System.Text.RegularExpressions;
using System.Web.Script.Serialization;
using UdpSim.Core.Icd;

internal static class PacketCheck
{
    private static readonly JavaScriptSerializer Json = new JavaScriptSerializer { MaxJsonLength = 2000000 };

    public static int Main(string[] args)
    {
        string reportPath = null;
        var report = new Dictionary<string, object> {
            { "status", "PACKET_FAIL" }, { "errors", new List<string>() },
            { "fields", new List<object>() }, { "warnings", new List<string>() }
        };
        var errors = (List<string>)report["errors"];
        try {
            var options = new Dictionary<string, string>(StringComparer.Ordinal);
            for (int i = 0; i < args.Length; i += 2) {
                if (i + 1 >= args.Length || !new[] { "--icd", "--payload", "--format", "--message", "--expected", "--seq", "--report" }.Contains(args[i]))
                    throw new ArgumentException("Unknown or incomplete packet option.");
                if (options.ContainsKey(args[i])) throw new ArgumentException("Duplicate packet option: " + args[i]);
                options.Add(args[i], args[i + 1]);
            }
            foreach (var key in new[] { "--icd", "--payload", "--format", "--message" })
                if (!options.ContainsKey(key)) throw new ArgumentException("Missing option " + key);
            options.TryGetValue("--report", out reportPath);
            foreach (var key in new[] { "--icd", "--payload", "--expected" }) {
                if (reportPath != null && options.ContainsKey(key) && string.Equals(Path.GetFullPath(reportPath), Path.GetFullPath(options[key]), StringComparison.OrdinalIgnoreCase)) {
                    reportPath = null;
                    throw new ArgumentException("Report must not overwrite an input.");
                }
            }
            var loaded = IcdLoader.Load(options["--icd"]);
            if (!loaded.Usable) throw new ArgumentException("ICD is unusable: " + string.Join("; ", loaded.Errors.Select(e => e.ToString())));
            var icd = loaded.Document;
            var message = icd.AllMessages.FirstOrDefault(m => m.Code == options["--message"]);
            if (message == null) throw new ArgumentException("Expected message code is not in the ICD.");
            byte[] payload = ReadPayload(options["--payload"], options["--format"]);
            report["message"] = message.Code;
            report["direction"] = message.Direction.ToString();
            report["payload_hex"] = Hex(payload);
            report["bytes"] = payload.Length;
            report["endian"] = icd.Endian.ToString();
            var decoded = MessageCodec.Decode(icd, payload);
            if (decoded.Ignored) throw new ArgumentException("Core rejected payload: " + decoded.Ignore);
            if (decoded.Message.Code != message.Code) throw new ArgumentException("Decoded message is " + decoded.Message.Code + ", expected " + message.Code + ".");
            report["seq"] = decoded.Seq;
            report["warnings"] = decoded.Warnings;
            var fields = (List<object>)report["fields"];
            int offset = 0;
            foreach (var h in decoded.Header) {
                fields.Add(Row(h.Name, h.Field.TypeName, offset, h.Field.Size, h.Field.Width, Hex(payload.Skip(offset).Take(h.Field.Size).ToArray()), h.Value, h.Value, h.Text, h.Role.ToString(), null));
                offset += h.Field.Size;
            }
            foreach (var f in decoded.Fields) {
                var leaf = f.Leaf;
                fields.Add(Row(leaf.Path, leaf.Field.TypeName, leaf.Offset, leaf.Field.Size, leaf.Width,
                    Hex(payload.Skip(leaf.Offset).Take(leaf.Field.Size).ToArray()), f.Raw, f.Value, f.Text, "Body",
                    leaf.Bits == null ? null : (object)new[] { leaf.Bits.From, leaf.Bits.To }));
            }
            if (options.ContainsKey("--seq")) {
                long seq;
                if (!long.TryParse(options["--seq"], NumberStyles.None, CultureInfo.InvariantCulture, out seq) || seq < 0)
                    throw new ArgumentException("Expected seq must be a nonnegative decimal integer.");
                if (!decoded.Seq.HasValue || decoded.Seq.Value != seq) errors.Add("SEQ mismatch: expected " + seq + ", actual " + (decoded.Seq.HasValue ? decoded.Seq.Value.ToString() : "absent"));
            }
            report["expectation_count"] = 0;
            report["body_expectations_complete"] = false;
            report["editable_expectations_complete"] = false;
            string status = "PACKET_DECODE_PASS";
            if (options.ContainsKey("--expected")) {
                if (new FileInfo(options["--expected"]).Length > 1000000) throw new ArgumentException("Expected JSON exceeds 1 MB.");
                var expected = ReadExpected(File.ReadAllText(options["--expected"], Encoding.UTF8));
                if (expected == null || expected.Count == 0) throw new ArgumentException("Expected JSON must be a nonempty object of leaf paths to string values.");
                foreach (var item in expected) {
                    if (!(item.Value is string)) throw new ArgumentException("Expected value must be a string: " + item.Key);
                    var leaf = message.FindValueLeaf(item.Key);
                    long want;
                    string reason;
                    if (!ValueText.TryResolve(icd, leaf, (string)item.Value, out want, out reason)) {
                        errors.Add("Invalid expectation " + item.Key + ": " + reason);
                        continue;
                    }
                    var body = decoded.FindField(item.Key);
                    var header = decoded.Header.FirstOrDefault(h => h.Name == item.Key && h.Role == HeaderRole.None);
                    long actual = body != null ? body.Raw : header.Value;
                    if (want != actual) errors.Add("Value mismatch " + item.Key + ": expected raw " + want + ", actual raw " + actual);
                }
                bool bodyComplete = message.Leaves.All(l => expected.ContainsKey(l.Path));
                bool editableComplete = bodyComplete && message.HeaderLeaves.All(l => expected.ContainsKey(l.Path));
                report["expectation_count"] = expected.Count;
                report["body_expectations_complete"] = bodyComplete;
                report["editable_expectations_complete"] = editableComplete;
                status = editableComplete ? "PACKET_EXPECTED_MATCH" : "PACKET_EXPECTED_SUBSET_MATCH";
            }
            if (errors.Count == 0) report["status"] = status;
        }
        catch (Exception ex) { errors.Add(ex.Message); }
        string json = Json.Serialize(report);
        if (reportPath != null) {
            try {
                string parent = Path.GetDirectoryName(Path.GetFullPath(reportPath));
                Directory.CreateDirectory(parent);
                File.WriteAllText(reportPath, json + Environment.NewLine, new UTF8Encoding(false));
            }
            catch (Exception ex) { errors.Add("Could not write report: " + ex.Message); report["status"] = "PACKET_FAIL"; json = Json.Serialize(report); }
        }
        Console.OutputEncoding = new UTF8Encoding(false);
        Console.WriteLine(json);
        return errors.Count == 0 ? 0 : 1;
    }

    private static Dictionary<string, object> Row(string path, string type, int offset, int size, int width, string bytes, long raw, long value, string text, string role, object bits)
    {
        return new Dictionary<string, object> { { "path", path }, { "type", type }, { "offset", offset }, { "size", size },
            { "width", width }, { "raw_bytes", bytes }, { "raw", raw }, { "value", value }, { "text", text }, { "role", role }, { "bits", bits } };
    }

    private static string Hex(byte[] bytes)
    {
        return BitConverter.ToString(bytes).Replace('-', ' ');
    }

    private static Dictionary<string, object> ReadExpected(string source)
    {
        int position = 0;
        var result = new Dictionary<string, object>(StringComparer.Ordinal);
        Take(source, ref position, '{');
        SkipSpace(source, ref position);
        if (position < source.Length && source[position] == '}') {
            position++;
        }
        else {
            while (true) {
                string key = ReadString(source, ref position);
                Take(source, ref position, ':');
                string value = ReadString(source, ref position);
                if (result.ContainsKey(key)) throw new ArgumentException("Duplicate expected leaf: " + key);
                result.Add(key, value);
                SkipSpace(source, ref position);
                if (position < source.Length && source[position] == '}') { position++; break; }
                Take(source, ref position, ',');
            }
        }
        SkipSpace(source, ref position);
        if (position != source.Length) throw new ArgumentException("Trailing content in expected JSON.");
        return result;
    }

    private static void SkipSpace(string source, ref int position)
    {
        while (position < source.Length && (source[position] == ' ' || source[position] == '\t' || source[position] == '\r' || source[position] == '\n')) position++;
    }

    private static void Take(string source, ref int position, char want)
    {
        SkipSpace(source, ref position);
        if (position >= source.Length || source[position++] != want) throw new ArgumentException("Expected JSON must be an object of unique leaf paths to string values.");
    }

    private static string ReadString(string source, ref int position)
    {
        SkipSpace(source, ref position);
        int start = position;
        Take(source, ref position, '"');
        while (position < source.Length) {
            char current = source[position++];
            if (current < 32) throw new ArgumentException("Control character in expected JSON string.");
            if (current == '"') return Json.Deserialize<string>(source.Substring(start, position - start));
            if (current == '\\') {
                if (position >= source.Length || "\"\\/bfnrtu".IndexOf(source[position]) < 0) throw new ArgumentException("Invalid expected JSON escape.");
                position++;
            }
        }
        throw new ArgumentException("Unterminated expected JSON string.");
    }

    private static byte[] ReadPayload(string path, string format)
    {
        var info = new FileInfo(path);
        if (format == "binary") {
            if (info.Length > 65507) throw new ArgumentException("UDP payload exceeds 65507 bytes.");
            return File.ReadAllBytes(path);
        }
        if (format != "hex") throw new ArgumentException("Format must be hex or binary.");
        if (info.Length > 400000) throw new ArgumentException("Hex payload input exceeds 400000 bytes.");
        string source = File.ReadAllText(path, Encoding.UTF8);
        if (!Regex.IsMatch(source, @"\A[0-9a-fA-F\s:]*\z")) throw new ArgumentException("Hex payload accepts only hexadecimal digits, whitespace and colon separators; no offsets or headers.");
        string hex = Regex.Replace(source, @"[\s:]", "");
        if (hex.Length % 2 != 0) throw new ArgumentException("Hex payload has an odd digit count.");
        if (hex.Length / 2 > 65507) throw new ArgumentException("UDP payload exceeds 65507 bytes.");
        var result = new byte[hex.Length / 2];
        for (int i = 0; i < result.Length; i++) result[i] = byte.Parse(hex.Substring(i * 2, 2), NumberStyles.HexNumber, CultureInfo.InvariantCulture);
        return result;
    }
}
