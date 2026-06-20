import AppKit
import Foundation
import SwiftUI

private enum HermesPaths {
    static let home = "/Users/bobeenlee"
    static let hermes = "\(home)/.local/bin/hermes"
    static let logs = "\(home)/.hermes/logs"
    static let workspace = "\(home)/Workspaces/hermes-workspace"
    static let path = "\(home)/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
}

private struct ManagedCommand: Identifiable {
    let id = UUID()
    let title: String
    let systemImage: String
    let shell: String
    let role: ButtonRole?

    init(_ title: String, systemImage: String, role: ButtonRole? = nil, shell: String) {
        self.title = title
        self.systemImage = systemImage
        self.role = role
        self.shell = shell
    }
}

@MainActor
private final class CommandModel: ObservableObject {
    @Published var output = "Ready."
    @Published var status = "Idle"
    @Published var isRunning = false
    @Published var endpoint = "http://127.0.0.1:8000/v1"
    @Published var hermesRunning = false
    @Published var localLLMRunning = false
    @Published var hermesStateText = "Unknown"
    @Published var localLLMStateText = "Unknown"

    private var task: Process?

    func refresh() {
        run(title: "Refresh", shell: Self.statusScript(endpoint: endpoint), parseStatus: true)
    }

    func run(_ command: ManagedCommand) {
        run(title: command.title, shell: command.shell)
    }

    func setHermesRunning(_ shouldRun: Bool) {
        let action = shouldRun ? "start" : "stop"
        run(
            title: shouldRun ? "Start Hermes Agent" : "Stop Hermes Agent",
            shell: """
            "\(HermesPaths.hermes)" gateway \(action)
            \(Self.statusScript(endpoint: endpoint))
            """,
            parseStatus: true
        )
    }

    func setLocalLLMRunning(_ shouldRun: Bool) {
        run(
            title: shouldRun ? "Start Local LLM" : "Stop Local LLM",
            shell: """
            \(shouldRun ? Self.startLocalLLMScript() : Self.stopLocalLLMScript())
            \(Self.statusScript(endpoint: endpoint))
            """,
            parseStatus: true
        )
    }

    func run(title: String, shell: String, parseStatus: Bool = false) {
        guard !isRunning else { return }
        isRunning = true
        status = "Running \(title)"
        output = "$ \(title)\n\n"
        var capturedOutput = ""

        let process = Process()
        let pipe = Pipe()
        process.executableURL = URL(fileURLWithPath: "/bin/zsh")
        process.arguments = ["-lc", shell]
        process.environment = [
            "PATH": HermesPaths.path,
            "HOME": HermesPaths.home,
            "LC_ALL": "en_US.UTF-8",
        ]
        process.standardOutput = pipe
        process.standardError = pipe
        task = process

        pipe.fileHandleForReading.readabilityHandler = { [weak self] handle in
            let data = handle.availableData
            guard !data.isEmpty, let text = String(data: data, encoding: .utf8) else { return }
            Task { @MainActor in
                capturedOutput.append(text)
                self?.output.append(text)
            }
        }

        DispatchQueue.global(qos: .userInitiated).async {
            do {
                try process.run()
                process.waitUntilExit()
                let code = process.terminationStatus
                DispatchQueue.main.async {
                    pipe.fileHandleForReading.readabilityHandler = nil
                    if parseStatus {
                        self.parseStatusMarkers(capturedOutput)
                    }
                    self.status = code == 0 ? "Finished \(title)" : "Finished \(title) with exit \(code)"
                    self.output.append("\n[exit \(code)]")
                    self.isRunning = false
                    self.task = nil
                }
            } catch {
                DispatchQueue.main.async {
                    pipe.fileHandleForReading.readabilityHandler = nil
                    self.status = "Failed \(title)"
                    self.output.append("\n\(error.localizedDescription)")
                    self.isRunning = false
                    self.task = nil
                }
            }
        }
    }

    func stopCurrentCommand() {
        task?.terminate()
        status = "Stopping"
    }

    func copyOutput() {
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(output, forType: .string)
    }

    func openLogs() {
        NSWorkspace.shared.open(URL(fileURLWithPath: HermesPaths.logs, isDirectory: true))
    }

    private func parseStatusMarkers(_ text: String) {
        if let value = marker("__HERMES_RUNNING", in: text) {
            hermesRunning = value == "1"
            hermesStateText = hermesRunning ? "Running" : "Stopped"
        }
        if let value = marker("__LOCAL_LLM_RUNNING", in: text) {
            localLLMRunning = value == "1"
            localLLMStateText = localLLMRunning ? "Running" : "Stopped"
        }
    }

    private func marker(_ name: String, in text: String) -> String? {
        text
            .split(separator: "\n")
            .last { $0.hasPrefix("\(name)=") }?
            .split(separator: "=", maxSplits: 1)
            .last
            .map(String.init)
    }

    static func statusScript(endpoint: String) -> String {
        """
        set +e
        export PATH="\(HermesPaths.path)"
        endpoint="\(escape(endpoint))"

        hermes_running=0
        "\(HermesPaths.hermes)" gateway status 2>&1 | grep -Eq 'Status:[[:space:]]+.*running|PID' && hermes_running=1

        local_llm_running=0
        pgrep -fl 'ollama|vllm|sglang|llama-server' >/dev/null 2>&1 && local_llm_running=1
        curl -fsS --max-time 3 "${endpoint%/}/models" >/tmp/hermes-mac-manager-endpoint.json 2>/tmp/hermes-mac-manager-endpoint.err && local_llm_running=1

        echo "__HERMES_RUNNING=$hermes_running"
        echo "__LOCAL_LLM_RUNNING=$local_llm_running"

        echo "== host =="
        hostname
        whoami
        date

        echo
        echo "== hermes gateway =="
        "\(HermesPaths.hermes)" gateway status 2>&1

        echo
        echo "== hermes status =="
        "\(HermesPaths.hermes)" status 2>&1 | sed -n '1,95p'

        echo
        echo "== local llm processes =="
        /bin/ps -axo pid,etime,stat,command | /usr/bin/grep -Ei 'ollama|vllm|sglang|llama-server' | /usr/bin/grep -v grep || echo "none"

        echo
        echo "== endpoint: ${endpoint%/}/models =="
        curl -fsS --max-time 5 "${endpoint%/}/models" >/tmp/hermes-mac-manager-endpoint.json 2>/tmp/hermes-mac-manager-endpoint.err
        if [ "$?" = "0" ]; then
          head -c 1600 /tmp/hermes-mac-manager-endpoint.json
        else
          echo
          cat /tmp/hermes-mac-manager-endpoint.err
          echo "endpoint check failed"
        fi

        echo
        echo
        echo "== common local endpoints =="
        for base in "http://127.0.0.1:11434/v1" "http://127.0.0.1:8000/v1"; do
          printf "%s " "$base"
          curl -fsS --max-time 3 "${base}/models" >/tmp/hermes-mac-manager-models.json 2>/tmp/hermes-mac-manager-models.err
          if [ "$?" = "0" ]; then
            echo "ok"
            head -c 700 /tmp/hermes-mac-manager-models.json
            echo
          else
            echo "unreachable"
          fi
        done

        echo
        echo "== recent gateway errors =="
        tail -40 "\(HermesPaths.logs)/gateway.error.log" 2>/dev/null || echo "no gateway.error.log"
        """
    }

    private static func startLocalLLMScript() -> String {
        """
        set -e
        export PATH="\(HermesPaths.path)"
        mkdir -p "\(HermesPaths.logs)"
        if command -v ollama >/dev/null 2>&1; then
          if pgrep -fl 'ollama serve' >/dev/null 2>&1; then
            echo "ollama serve already running"
          else
            nohup ollama serve > "\(HermesPaths.logs)/ollama.log" 2>&1 &
            sleep 2
          fi
          curl -fsS --max-time 5 http://127.0.0.1:11434/v1/models
        elif open -gja Ollama; then
          echo "Opened Ollama.app"
          sleep 2
        else
          echo "Ollama is not installed on this Mac."
          exit 1
        fi
        """
    }

    private static func stopLocalLLMScript() -> String {
        """
        set +e
        pkill -f 'ollama serve'
        osascript -e 'quit app "Ollama"' >/dev/null 2>&1
        sleep 1
        /bin/ps -axo pid,etime,stat,command | /usr/bin/grep -Ei 'ollama' | /usr/bin/grep -v grep || echo "ollama stopped"
        """
    }

    private static func escape(_ value: String) -> String {
        value.replacingOccurrences(of: "\"", with: "\\\"")
    }
}

private enum Commands {
    static let restartHermes = ManagedCommand("Restart", systemImage: "arrow.clockwise", shell: """
        "\(HermesPaths.hermes)" gateway restart && "\(HermesPaths.hermes)" gateway status
        """)

    static let openModel = ManagedCommand("Open Model", systemImage: "terminal", shell: """
        osascript <<'OSA'
        tell application "Terminal"
          activate
          do script "export PATH=\\"\(HermesPaths.path)\\"; cd \(HermesPaths.workspace); \(HermesPaths.hermes) model"
        end tell
        OSA
        """)

    static func checkEndpoint(_ endpoint: String) -> ManagedCommand {
        ManagedCommand("Check Endpoint", systemImage: "network", shell: """
        set +e
        endpoint="\(endpoint.replacingOccurrences(of: "\"", with: "\\\""))"
        echo "${endpoint%/}/models"
        curl -fsS --max-time 8 "${endpoint%/}/models"
        """)
    }
}

private struct CommandButton: View {
    let command: ManagedCommand
    let action: (ManagedCommand) -> Void

    var body: some View {
        Button(role: command.role) {
            action(command)
        } label: {
            Label(command.title, systemImage: command.systemImage)
                .frame(minWidth: 96)
        }
        .controlSize(.large)
    }
}

private struct ContentView: View {
    @StateObject private var model = CommandModel()

    var body: some View {
        VStack(spacing: 0) {
            header
            Divider()
            HStack(alignment: .top, spacing: 16) {
                controls
                output
            }
            .padding(16)
        }
        .frame(minWidth: 980, minHeight: 640)
        .onAppear { model.refresh() }
    }

    private var header: some View {
        HStack(spacing: 12) {
            Image(systemName: "server.rack")
                .font(.system(size: 28, weight: .semibold))
                .foregroundStyle(.blue)
            VStack(alignment: .leading, spacing: 2) {
                Text("Hermes Mac Manager")
                    .font(.title2.weight(.semibold))
                Text(model.status)
                    .font(.callout)
                    .foregroundStyle(.secondary)
            }
            Spacer()
            Button {
                model.refresh()
            } label: {
                Label("Refresh", systemImage: "arrow.clockwise")
            }
            .keyboardShortcut("r")
            .disabled(model.isRunning)

            Button(role: .cancel) {
                model.stopCurrentCommand()
            } label: {
                Label("Stop Command", systemImage: "xmark.circle")
            }
            .disabled(!model.isRunning)
        }
        .padding(16)
    }

    private var controls: some View {
        VStack(alignment: .leading, spacing: 18) {
            GroupBox("Hermes Gateway") {
                VStack(alignment: .leading, spacing: 12) {
                    stateToggle(
                        title: "Hermes Agent",
                        detail: model.hermesStateText,
                        isOn: Binding(
                            get: { model.hermesRunning },
                            set: { model.setHermesRunning($0) }
                        )
                    )
                    CommandButton(command: Commands.restartHermes) { command in
                        model.run(
                            title: command.title,
                            shell: command.shell + "\n" + CommandModel.statusScript(endpoint: model.endpoint),
                            parseStatus: true
                        )
                    }
                }
                .padding(.vertical, 4)
            }

            GroupBox("Local LLM") {
                VStack(alignment: .leading, spacing: 12) {
                    TextField("OpenAI-compatible endpoint", text: $model.endpoint)
                        .textFieldStyle(.roundedBorder)
                    stateToggle(
                        title: "Local LLM",
                        detail: model.localLLMStateText,
                        isOn: Binding(
                            get: { model.localLLMRunning },
                            set: { model.setLocalLLMRunning($0) }
                        )
                    )
                    HStack {
                        CommandButton(command: Commands.checkEndpoint(model.endpoint), action: model.run)
                        CommandButton(command: Commands.openModel, action: model.run)
                    }
                }
                .padding(.vertical, 4)
            }

            GroupBox("Files") {
                HStack {
                    Button {
                        model.openLogs()
                    } label: {
                        Label("Open Logs", systemImage: "folder")
                    }
                    Button {
                        model.copyOutput()
                    } label: {
                        Label("Copy Output", systemImage: "doc.on.doc")
                    }
                }
                .controlSize(.large)
                .padding(.vertical, 4)
            }

            Spacer(minLength: 0)
        }
        .frame(width: 410)
        .disabled(model.isRunning)
    }

    private func stateToggle(title: String, detail: String, isOn: Binding<Bool>) -> some View {
        HStack(spacing: 12) {
            VStack(alignment: .leading, spacing: 2) {
                Text(title)
                    .font(.headline)
                Text(detail)
                    .font(.callout.weight(.medium))
                    .foregroundStyle(isOn.wrappedValue ? .green : .secondary)
            }
            Spacer()
            Toggle("", isOn: isOn)
                .toggleStyle(.switch)
                .labelsHidden()
        }
        .padding(12)
        .background(Color(nsColor: .controlBackgroundColor))
        .clipShape(RoundedRectangle(cornerRadius: 8))
    }

    private var output: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Output")
                .font(.headline)
            ScrollView {
                Text(model.output)
                    .font(.system(.body, design: .monospaced))
                    .textSelection(.enabled)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(12)
            }
            .background(Color(nsColor: .textBackgroundColor))
            .clipShape(RoundedRectangle(cornerRadius: 8))
            .overlay(
                RoundedRectangle(cornerRadius: 8)
                    .stroke(Color(nsColor: .separatorColor))
            )
        }
    }
}

@main
struct HermesMacManagerApp: App {
    var body: some Scene {
        WindowGroup {
            ContentView()
        }
    }
}
