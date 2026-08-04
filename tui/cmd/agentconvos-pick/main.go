package main

import (
	"encoding/json"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"strings"

	"charm.land/bubbles/v2/key"
	"charm.land/huh/v2"
	"charm.land/lipgloss/v2"
	"github.com/charmbracelet/x/ansi"
	"github.com/charmbracelet/x/term"

	"github.com/testy-cool/agentconvos/tui/inlinepicker"
)

const (
	defaultWidth  = 100
	defaultHeight = 30
)

func main() {
	payload, err := loadPayload()
	if err != nil {
		fmt.Fprintln(os.Stderr, "agentconvos pick:", err)
		os.Exit(1)
	}

	width, height := terminalSize(os.Stdout)
	colorEnabled := term.IsTerminal(os.Stdout.Fd()) &&
		os.Getenv("NO_COLOR") == "" &&
		os.Getenv("TERM") != "dumb"
	selector := huhSelector(payload.Project, width, height, os.Stdin, os.Stdout)
	code := inlinepicker.Run(
		payload,
		os.Stdout,
		selector,
		inlinepicker.RenderOptions{Color: colorEnabled, Width: width},
	)
	if code != 0 {
		os.Exit(code)
	}
}

func loadPayload() (inlinepicker.ContextPayload, error) {
	backend := os.Getenv("AGENTCONVOS_BACKEND")
	if backend == "" {
		backend = "agentconvos"
	}
	command := exec.Command(backend, "--context", "--json")
	command.Stderr = os.Stderr
	data, err := command.Output()
	if err != nil {
		return inlinepicker.ContextPayload{}, fmt.Errorf("load current-project conversations: %w", err)
	}
	var payload inlinepicker.ContextPayload
	if err := json.Unmarshal(data, &payload); err != nil {
		return inlinepicker.ContextPayload{}, fmt.Errorf("decode backend response: %w", err)
	}
	return payload, nil
}

func huhSelector(project string, width, height int, input io.Reader, output io.Writer) inlinepicker.Selector {
	return func(options []inlinepicker.Option) (string, error) {
		selected := options[0].Value
		huhOptions := make([]huh.Option[string], 0, len(options))
		for _, option := range options {
			label := optionLabel(option, width)
			huhOptions = append(huhOptions, huh.NewOption(label, option.Value))
		}

		visibleRows := min(len(huhOptions), max(3, height-9))
		visibleRows = min(10, visibleRows)
		field := huh.NewSelect[string]().
			Title(projectHeading(project)).
			Options(huhOptions...).
			Value(&selected).
			Height(visibleRows)

		keymap := huh.NewDefaultKeyMap()
		keymap.Quit = key.NewBinding(key.WithKeys("esc", "ctrl+c"))
		keymap.Select.Submit.SetHelp("enter", "open")
		keymap.Select.Filter.SetHelp("/", "filter")
		keymap.Select.SetFilter.SetKeys("esc", "ctrl+c")
		keymap.Select.SetFilter.SetHelp("esc/ctrl+c", "cancel")
		keymap.Select.ClearFilter.SetKeys("esc", "ctrl+c")
		keymap.Select.ClearFilter.SetHelp("esc/ctrl+c", "cancel")
		keymap.Select.ClearFilter.SetEnabled(true)
		form := huh.NewForm(huh.NewGroup(field)).
			WithInput(input).
			WithOutput(output).
			WithAccessible(false).
			WithWidth(max(40, width)).
			WithTheme(neutralTheme()).
			WithKeyMap(keymap).
			WithShowHelp(true)
		if err := form.Run(); err != nil {
			return "", err
		}
		return selected, nil
	}
}

func optionLabel(option inlinepicker.Option, width int) string {
	metadata := option.Description
	available := max(24, width-8)
	if ansi.StringWidth(metadata)+8 >= available {
		return ansi.Truncate(option.Title+" · "+metadata, available, "…")
	}
	titleWidth := available - ansi.StringWidth(metadata) - 3
	return ansi.Truncate(option.Title, titleWidth, "…") + " · " + metadata
}

func projectHeading(project string) string {
	name := compactProjectName(project)
	if name == "" {
		return "agentconvos\nRecent conversations"
	}
	return fmt.Sprintf("agentconvos / %s\nRecent conversations", name)
}

func compactProjectName(project string) string {
	project = strings.TrimSpace(project)
	if project == "" {
		return ""
	}
	cleaned := filepath.Clean(project)
	name := filepath.Base(cleaned)
	if name == "." || name == string(filepath.Separator) {
		return project
	}
	return name
}

func neutralTheme() huh.Theme {
	return huh.ThemeFunc(func(isDark bool) *huh.Styles {
		styles := huh.ThemeBase(isDark)
		text := lipgloss.Color("#F2F2F2")
		muted := lipgloss.Color("#929292")
		accent := lipgloss.Color("#78A9D4")

		styles.Focused.Base = styles.Focused.Base.BorderForeground(accent)
		styles.Focused.Title = styles.Focused.Title.Foreground(text).Bold(true)
		styles.Focused.Description = styles.Focused.Description.Foreground(muted)
		styles.Focused.Option = styles.Focused.Option.Foreground(text)
		styles.Focused.SelectSelector = styles.Focused.SelectSelector.Foreground(accent).SetString("› ")
		styles.Focused.NextIndicator = styles.Focused.NextIndicator.Foreground(muted)
		styles.Focused.PrevIndicator = styles.Focused.PrevIndicator.Foreground(muted)
		styles.Focused.ErrorIndicator = styles.Focused.ErrorIndicator.Foreground(accent)
		styles.Focused.ErrorMessage = styles.Focused.ErrorMessage.Foreground(accent)
		styles.Focused.TextInput.Cursor = styles.Focused.TextInput.Cursor.Foreground(accent)
		styles.Focused.TextInput.Prompt = styles.Focused.TextInput.Prompt.Foreground(accent)
		styles.Focused.TextInput.Text = styles.Focused.TextInput.Text.Foreground(text)
		styles.Focused.TextInput.Placeholder = styles.Focused.TextInput.Placeholder.Foreground(muted)
		styles.Blurred = styles.Focused
		styles.Blurred.Base = styles.Blurred.Base.BorderStyle(lipgloss.HiddenBorder())
		styles.Group.Title = styles.Focused.Title
		styles.Group.Description = styles.Focused.Description
		styles.Help.ShortKey = styles.Help.ShortKey.Foreground(muted)
		styles.Help.ShortDesc = styles.Help.ShortDesc.Foreground(muted)
		styles.Help.ShortSeparator = styles.Help.ShortSeparator.Foreground(muted)
		styles.Help.FullKey = styles.Help.FullKey.Foreground(muted)
		styles.Help.FullDesc = styles.Help.FullDesc.Foreground(muted)
		styles.Help.FullSeparator = styles.Help.FullSeparator.Foreground(muted)
		styles.Help.Ellipsis = styles.Help.Ellipsis.Foreground(muted)
		return styles
	})
}

func terminalSize(file *os.File) (int, int) {
	width, height, err := term.GetSize(file.Fd())
	if err != nil || width <= 0 || height <= 0 {
		return defaultWidth, defaultHeight
	}
	return width, height
}
