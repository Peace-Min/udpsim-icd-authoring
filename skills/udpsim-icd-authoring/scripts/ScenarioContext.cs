using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using System.Web.Script.Serialization;
using UdpSim.Core.Config;
using UdpSim.Core.Icd;

internal static class ScenarioContext
{
    private static Dictionary<string, object> D(params object[] pairs)
    {
        var value = new Dictionary<string, object>();
        for (int i = 0; i < pairs.Length; i += 2) value.Add((string)pairs[i], pairs[i + 1]);
        return value;
    }

    private static string Hash(string path)
    {
        using (var hash = SHA256.Create())
            return BitConverter.ToString(hash.ComputeHash(File.ReadAllBytes(path))).Replace("-", "").ToLowerInvariant();
    }

    private static object Leaf(IcdDocument icd, IcdLeaf leaf)
    {
        var definition = icd.FindEnum(leaf.EnumName);
        var items = definition == null ? new object[0] : definition.Items.Select(i => (object)D("name", i.Name, "value", i.Value)).ToArray();
        return D("path", leaf.Path, "type", leaf.Field.TypeName, "width", leaf.Width,
                 "signed", leaf.IsSigned, "enum", leaf.EnumName, "enum_items", items);
    }

    private static object Message(IcdDocument icd, IcdMessage message)
    {
        return D("code", message.Code, "name", message.Name, "id", message.Id, "length", message.ComputedLength,
                 "body", message.Leaves.Select(l => Leaf(icd, l)).ToArray(),
                 "user_header", message.HeaderLeaves.Select(l => Leaf(icd, l)).ToArray(),
                 "automatic_header", icd.Header.Where(f => f.Role != HeaderRole.None).Select(f => f.Name).ToArray());
    }

    public static int Main(string[] args)
    {
        Console.OutputEncoding = new UTF8Encoding(false);
        try
        {
            var options = new Dictionary<string, string>();
            for (int i = 0; i < args.Length; i += 2)
            {
                if (i + 1 >= args.Length || !new[] { "--config", "--output", "--app", "--skill", "--icd" }.Contains(args[i]) || options.ContainsKey(args[i]))
                    throw new ArgumentException("Unknown, duplicate or incomplete context option.");
                options.Add(args[i], args[i + 1]);
            }
            foreach (string key in new[] { "--config", "--output", "--app", "--skill" })
                if (!options.ContainsKey(key)) throw new ArgumentException("Missing " + key);
            string configPath = Path.GetFullPath(options["--config"]);
            string output = Path.GetFullPath(options["--output"]);
            if (!string.Equals(Path.GetExtension(output), ".json", StringComparison.OrdinalIgnoreCase)) throw new ArgumentException("Output must end in .json.");
            var loaded = SimConfigLoader.Load(configPath);
            if (!loaded.Ok) throw new ArgumentException(loaded.Error ?? "Config not found");
            var catalog = IcdCatalog.Load(loaded.Config, Path.GetDirectoryName(configPath));
            var validation = ConfigValidator.Validate(loaded.Config, catalog);
            if (validation.HasErrors) throw new ArgumentException(string.Join("; ", validation.AllMessages(loaded.Config)));
            var sources = new HashSet<string>(StringComparer.OrdinalIgnoreCase) { configPath };
            foreach (string key in catalog.Keys) sources.Add(catalog.Get(key).FullPath);
            foreach (string folder in new[] { "src/UdpSim.Core", "tools/xml" })
            {
                string basePath = Path.Combine(options["--app"], folder);
                foreach (string file in Directory.GetFiles(basePath, "*", SearchOption.AllDirectories))
                {
                    string normalized = file.Replace('\\', '/');
                    if (normalized.Contains("/obj/") || normalized.Contains("/bin/")) continue;
                    if (new[] { ".cs", ".csproj", ".ps1", ".xsd" }.Contains(Path.GetExtension(file))) sources.Add(Path.GetFullPath(file));
                }
            }
            foreach (string name in new[] { "ScenarioContext.cs", "Export-ScenarioContext.ps1", "Test-ScenarioXml.ps1", "scenario_tool.py", "icd_tool.py" })
                sources.Add(Path.GetFullPath(Path.Combine(options["--skill"], "scripts", name)));
            if (sources.Contains(output)) throw new ArgumentException("Context must not overwrite an input/tool source.");
            var icds = new List<object>();
            foreach (string key in catalog.Keys)
            {
                if (options.ContainsKey("--icd") && key != options["--icd"]) continue;
                var icd = catalog.GetDocument(key);
                icds.Add(D("key", key, "targets", loaded.Config.Links.Where(l => l.Enabled && l.Icd == key).Select(l => l.Name).ToArray(),
                           "send", icd.Send.Select(m => Message(icd, m)).ToArray(),
                           "receive", icd.Receive.Select(m => Message(icd, m)).ToArray()));
            }
            if (icds.Count == 0) throw new ArgumentException("Selected ICD key not present in Config (case-sensitive).");
            var context = D("context_version", 1, "config_path", configPath, "config_name", loaded.Config.Name,
                            "core_sha256", Hash(typeof(IcdLoader).Assembly.Location), "icds", icds,
                            "sources", sources.OrderBy(p => p, StringComparer.Ordinal).Select(p => D("path", p, "sha256", Hash(p))).ToArray());
            string json = new JavaScriptSerializer { MaxJsonLength = 32000000 }.Serialize(context);
            Directory.CreateDirectory(Path.GetDirectoryName(output));
            string temp = output + "." + Guid.NewGuid().ToString("N") + ".tmp";
            File.WriteAllText(temp, json + Environment.NewLine, new UTF8Encoding(false));
            try { if (File.Exists(output)) File.Replace(temp, output, null); else File.Move(temp, output); }
            finally { if (File.Exists(temp)) File.Delete(temp); }
            Console.WriteLine("CONTEXT_EXPORTED: real Core leaves; strict validation performed by caller; " + output);
            return 0;
        }
        catch (Exception error) { Console.Error.WriteLine("CONTEXT_FAIL: " + error.Message); return 1; }
    }
}
