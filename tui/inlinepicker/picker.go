package inlinepicker

import (
	"errors"
	"fmt"
	"io"
	"path/filepath"
	"regexp"
	"sort"
	"strings"
	"time"

	"charm.land/glamour/v2"
	"charm.land/glamour/v2/styles"
	"charm.land/huh/v2"
	"charm.land/lipgloss/v2"
)

// Conversation is the normalized catch-up record emitted by
// agentconvos --context --json.
type Conversation struct {
	UUID             string `json:"uuid"`
	Slug             string `json:"slug"`
	Source           string `json:"source"`
	Timestamp        string `json:"timestamp"`
	TurnCount        int    `json:"turn_count"`
	Model            string `json:"model"`
	Effort           string `json:"effort"`
	Summary          string `json:"summary"`
	FirstMessage     string `json:"first_message"`
	LastUserMessage  string `json:"last_user_message"`
	LastAgentMessage string `json:"last_agent_message"`
}

// ContextPayload is the current-project response from agentconvos.
type ContextPayload struct {
	Project       string         `json:"project"`
	Conversations []Conversation `json:"conversations"`
}

// Option is a presentation-neutral picker option.
type Option struct {
	Title       string
	Description string
	Value       string
}

// RenderOptions controls terminal-aware detail rendering.
type RenderOptions struct {
	Color bool
	Width int
}

// Selector owns only the interactive prompt lifecycle.
type Selector func([]Option) (string, error)

var (
	whitespace         = regexp.MustCompile(`\s+`)
	markdownDecoration = regexp.MustCompile("[*`~]")
	markdownLink       = regexp.MustCompile(`\[([^]]+)]\([^)]+\)`)
)

// RecentPerSource applies the product cap defensively even when an older
// backend returns more records, then restores global recency order.
func RecentPerSource(conversations []Conversation, limit int) []Conversation {
	if limit <= 0 {
		return nil
	}
	ordered := append([]Conversation(nil), conversations...)
	sort.SliceStable(ordered, func(left, right int) bool {
		return ordered[left].Timestamp > ordered[right].Timestamp
	})

	counts := make(map[string]int)
	selected := make([]Conversation, 0, len(ordered))
	for _, conversation := range ordered {
		if counts[conversation.Source] >= limit {
			continue
		}
		counts[conversation.Source]++
		selected = append(selected, conversation)
	}
	return selected
}

// Options turns normalized records into concise, scannable picker rows.
func Options(conversations []Conversation) []Option {
	options := make([]Option, 0, len(conversations))
	for _, conversation := range conversations {
		options = append(options, Option{
			Title: conversationTitle(conversation),
			Description: strings.Join(nonEmpty(
				strings.ToLower(conversation.Source),
				formatDate(conversation.Timestamp),
				turnLabel(conversation.TurnCount),
			), " · "),
			Value: conversation.UUID,
		})
	}
	return options
}

// Run completes selection before writing the chosen conversation so the
// result remains as an ordinary shell-scrollback document.
func Run(payload ContextPayload, output io.Writer, selector Selector, renderOptions RenderOptions) int {
	conversations := RecentPerSource(payload.Conversations, 5)
	if len(conversations) == 0 {
		if payload.Project != "" {
			fmt.Fprintf(output, "No conversations found for %s.\n", payload.Project)
		} else {
			fmt.Fprintln(output, "No conversations found.")
		}
		return 0
	}

	selectedID, err := selector(Options(conversations))
	if errors.Is(err, huh.ErrUserAborted) {
		return 0
	}
	if err != nil {
		fmt.Fprintf(output, "agentconvos pick: %v\n", err)
		return 1
	}

	var selected *Conversation
	for index := range conversations {
		if conversations[index].UUID == selectedID {
			selected = &conversations[index]
			break
		}
	}
	if selected == nil {
		fmt.Fprintln(output, "agentconvos pick: selected conversation is unavailable")
		return 1
	}

	detail, err := RenderDetail(payload, *selected, renderOptions)
	if err != nil {
		fmt.Fprintf(output, "agentconvos pick: %v\n", err)
		return 1
	}
	_, _ = fmt.Fprintln(output, detail)
	return 0
}

// RenderDetail builds the complete post-selection scrollback document.
func RenderDetail(payload ContextPayload, conversation Conversation, options RenderOptions) (string, error) {
	width := options.Width
	if width <= 0 {
		width = 100
	}
	width = max(24, width-2)

	titleStyle := lipgloss.NewStyle()
	metaStyle := lipgloss.NewStyle()
	labelStyle := lipgloss.NewStyle()
	if options.Color {
		titleStyle = titleStyle.Foreground(lipgloss.Color("#F2F2F2")).Bold(true)
		metaStyle = metaStyle.Foreground(lipgloss.Color("#929292"))
		labelStyle = labelStyle.Foreground(lipgloss.Color("#F2F2F2")).Bold(true)
	}

	var document strings.Builder
	document.WriteString("\n")
	document.WriteString(titleStyle.Render("Opened " + conversationTitle(conversation)))
	document.WriteString("\n")

	if project := compactProjectName(payload.Project); project != "" {
		document.WriteString(metaStyle.Render(project))
		document.WriteString("\n")
	}
	context := nonEmpty(
		formatDate(conversation.Timestamp),
		strings.ToLower(conversation.Source),
		conversation.Model,
		conversation.Effort,
		turnLabel(conversation.TurnCount),
	)
	if len(context) > 0 {
		document.WriteString(metaStyle.Render(strings.Join(context, " · ")))
		document.WriteString("\n")
	}

	sections := []struct {
		label string
		text  string
	}{
		{label: "Recap", text: conversation.Summary},
		{label: "First message", text: conversation.FirstMessage},
	}
	if normalized(conversation.LastUserMessage) != normalized(conversation.FirstMessage) {
		sections = append(sections, struct {
			label string
			text  string
		}{label: "Your latest message", text: conversation.LastUserMessage})
	}
	sections = append(sections, struct {
		label string
		text  string
	}{label: "Agent reply", text: conversation.LastAgentMessage})

	for _, section := range sections {
		if strings.TrimSpace(section.text) == "" {
			continue
		}
		rendered, err := renderMarkdown(section.text, width, options.Color)
		if err != nil {
			return "", fmt.Errorf("render %s: %w", strings.ToLower(section.label), err)
		}
		document.WriteString("\n")
		document.WriteString(labelStyle.Render(section.label))
		document.WriteString("\n")
		document.WriteString(strings.Trim(rendered, "\n"))
		document.WriteString("\n")
	}

	return strings.TrimRight(document.String(), "\n"), nil
}

func renderMarkdown(markdown string, width int, colorEnabled bool) (string, error) {
	style := styles.NoTTYStyleConfig
	zero := uint(0)
	style.Document.Margin = &zero
	style.H1.Prefix = ""
	style.H2.Prefix = ""
	style.H3.Prefix = ""
	style.H4.Prefix = ""
	style.H5.Prefix = ""
	style.H6.Prefix = ""
	style.Strong.BlockPrefix = ""
	style.Strong.BlockSuffix = ""
	style.Emph.BlockPrefix = ""
	style.Emph.BlockSuffix = ""
	style.Strikethrough.BlockPrefix = ""
	style.Strikethrough.BlockSuffix = ""
	style.Code.BlockPrefix = ""
	style.Code.BlockSuffix = ""
	if colorEnabled {
		text := "#F2F2F2"
		muted := "#929292"
		accent := "#78A9D4"
		enabled := true
		style.Document.Color = &text
		style.Paragraph.Color = &text
		style.Text.Color = &text
		style.Heading.Color = &text
		style.Heading.Bold = &enabled
		style.H1.Color = &text
		style.H2.Color = &text
		style.H3.Color = &text
		style.H4.Color = &text
		style.H5.Color = &text
		style.H6.Color = &text
		style.Strong.Color = &text
		style.Strong.Bold = &enabled
		style.Emph.Color = &text
		style.Emph.Italic = &enabled
		style.Strikethrough.CrossedOut = &enabled
		style.Item.Color = &text
		style.Enumeration.Color = &muted
		style.BlockQuote.Color = &muted
		style.Link.Color = &accent
		style.LinkText.Color = &accent
		style.Code.Color = &text
		style.Code.BackgroundColor = nil
		style.CodeBlock.Color = &text
		style.CodeBlock.BackgroundColor = nil
		style.CodeBlock.Theme = ""
		style.CodeBlock.Chroma = nil
	}

	renderer, err := glamour.NewTermRenderer(
		glamour.WithStyles(style),
		glamour.WithWordWrap(max(20, width)),
		glamour.WithPreservedNewLines(),
	)
	if err != nil {
		return "", err
	}
	defer renderer.Close()
	return renderer.Render(markdown)
}

func conversationTitle(conversation Conversation) string {
	if title := firstTextLine(conversation.Summary); title != "" {
		return title
	}
	if slug := strings.TrimSpace(conversation.Slug); slug != "" {
		return humanizeIdentifier(slug)
	}
	if title := firstTextLine(conversation.FirstMessage); title != "" {
		return humanizeDelegatedTitle(title)
	}
	return "Untitled conversation"
}

func firstTextLine(value string) string {
	for _, line := range strings.Split(value, "\n") {
		line = strings.TrimSpace(strings.TrimLeft(strings.TrimSpace(line), "#"))
		if line == "" {
			continue
		}
		line = markdownLink.ReplaceAllString(line, "$1")
		line = markdownDecoration.ReplaceAllString(line, "")
		return whitespace.ReplaceAllString(strings.TrimSpace(line), " ")
	}
	return ""
}

func humanizeIdentifier(value string) string {
	value = strings.NewReplacer("_", " ", "-", " ").Replace(value)
	return whitespace.ReplaceAllString(strings.TrimSpace(value), " ")
}

func humanizeDelegatedTitle(value string) string {
	const prefix = "[delegated task]"
	const suffix = "(prompt not recorded)"
	lower := strings.ToLower(value)
	if strings.HasPrefix(lower, prefix) {
		value = strings.TrimSpace(value[len(prefix):])
		if strings.HasSuffix(strings.ToLower(value), suffix) {
			value = strings.TrimSpace(value[:len(value)-len(suffix)])
		}
		return humanizeIdentifier(value)
	}
	return value
}

func formatDate(value string) string {
	if value == "" {
		return ""
	}
	parsed, err := time.Parse(time.RFC3339Nano, value)
	if err != nil {
		return ""
	}
	return parsed.Format("02 Jan 2006")
}

func turnLabel(turns int) string {
	if turns <= 0 {
		return ""
	}
	if turns == 1 {
		return "1 turn"
	}
	return fmt.Sprintf("%d turns", turns)
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

func normalized(value string) string {
	return whitespace.ReplaceAllString(strings.TrimSpace(value), " ")
}

func nonEmpty(values ...string) []string {
	result := make([]string, 0, len(values))
	for _, value := range values {
		if strings.TrimSpace(value) != "" {
			result = append(result, value)
		}
	}
	return result
}
