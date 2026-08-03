package main

import (
	"encoding/json"
	"fmt"
	"image/color"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"strings"

	"charm.land/bubbles/v2/help"
	"charm.land/bubbles/v2/key"
	"charm.land/bubbles/v2/list"
	"charm.land/bubbles/v2/viewport"
	tea "charm.land/bubbletea/v2"
	"charm.land/lipgloss/v2"
)

type conversation struct {
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

type contextPayload struct {
	Project       string         `json:"project"`
	Conversations []conversation `json:"conversations"`
}

type conversationItem struct {
	conversation conversation
}

func (item conversationItem) Title() string {
	if strings.TrimSpace(item.conversation.Slug) != "" {
		return item.conversation.Slug
	}
	return compact(item.conversation.FirstMessage, 120)
}

func (item conversationItem) Description() string {
	c := item.conversation
	return strings.Join(nonEmpty(
		shortDate(c.Timestamp),
		strings.ToLower(c.Source),
		turnLabel(c.TurnCount),
	), " · ")
}

func (item conversationItem) FilterValue() string {
	c := item.conversation
	return strings.Join([]string{c.Slug, c.Source, c.FirstMessage, c.LastUserMessage, c.LastAgentMessage}, " ")
}

type conversationDelegate struct {
	colors  palette
	focused bool
}

func (d conversationDelegate) Height() int  { return 2 }
func (d conversationDelegate) Spacing() int { return 1 }
func (d conversationDelegate) Update(_ tea.Msg, _ *list.Model) tea.Cmd {
	return nil
}

func (d conversationDelegate) Render(w io.Writer, m list.Model, index int, raw list.Item) {
	item, ok := raw.(conversationItem)
	if !ok {
		return
	}

	selected := index == m.Index()
	rowWidth := max(1, m.Width())
	textWidth := max(1, rowWidth-3)
	marker := "  "
	if selected {
		marker = "▌ "
	}

	titleStyle := lipgloss.NewStyle().
		Width(rowWidth).
		Foreground(d.colors.text)
	metaStyle := lipgloss.NewStyle().
		Width(rowWidth).
		Foreground(d.colors.muted)
	if selected {
		titleStyle = titleStyle.Bold(true).Background(d.colors.surface)
		metaStyle = metaStyle.Background(d.colors.surface)
		if d.focused {
			titleStyle = titleStyle.Foreground(d.colors.primary)
		}
	}

	title := marker + compact(item.Title(), textWidth)
	metadata := marker + compact(item.Description(), textWidth)
	_, _ = io.WriteString(w, titleStyle.Render(title)+"\n"+metaStyle.Render(metadata))
}

var whitespace = regexp.MustCompile(`\s+`)

type palette struct {
	canvas    color.Color
	panel     color.Color
	surface   color.Color
	text      color.Color
	muted     color.Color
	border    color.Color
	primary   color.Color
	secondary color.Color
	onPrimary color.Color
}

func newPalette(isDark bool) palette {
	lightDark := lipgloss.LightDark(isDark)
	return palette{
		canvas:    lightDark(lipgloss.Color("#FBF8FC"), lipgloss.Color("#18171F")),
		panel:     lightDark(lipgloss.Color("#F4EFF6"), lipgloss.Color("#201E29")),
		surface:   lightDark(lipgloss.Color("#EAE2EE"), lipgloss.Color("#302B3A")),
		text:      lightDark(lipgloss.Color("#27222D"), lipgloss.Color("#F4F0F5")),
		muted:     lightDark(lipgloss.Color("#716978"), lipgloss.Color("#AAA1AE")),
		border:    lightDark(lipgloss.Color("#D7CCDC"), lipgloss.Color("#463F50")),
		primary:   lightDark(lipgloss.Color("#7557B7"), lipgloss.Color("#C6A0F6")),
		secondary: lightDark(lipgloss.Color("#B5356E"), lipgloss.Color("#F5A9CB")),
		onPrimary: lightDark(lipgloss.Color("#FFF9FF"), lipgloss.Color("#211A29")),
	}
}

type paneFocus int

const (
	browseFocus paneFocus = iota
	detailFocus
)

type keyMap struct {
	Move       key.Binding
	Scroll     key.Binding
	Page       key.Binding
	Ends       key.Binding
	SwitchPane key.Binding
	BrowsePane key.Binding
	Search     key.Binding
	Apply      key.Binding
	Clear      key.Binding
	Quit       key.Binding
}

func defaultKeyMap() keyMap {
	return keyMap{
		Move: key.NewBinding(
			key.WithKeys("up", "down", "j", "k"),
			key.WithHelp("j/k", "move"),
		),
		Scroll: key.NewBinding(
			key.WithKeys("up", "down", "j", "k"),
			key.WithHelp("j/k", "scroll"),
		),
		Page: key.NewBinding(
			key.WithKeys("pgup", "pgdown"),
			key.WithHelp("pgup/dn", "page"),
		),
		Ends: key.NewBinding(
			key.WithKeys("home", "end", "g", "G"),
			key.WithHelp("g/G", "ends"),
		),
		SwitchPane: key.NewBinding(
			key.WithKeys("tab"),
			key.WithHelp("tab", "read"),
		),
		BrowsePane: key.NewBinding(
			key.WithKeys("tab"),
			key.WithHelp("tab", "browse"),
		),
		Search: key.NewBinding(
			key.WithKeys("/"),
			key.WithHelp("/", "filter"),
		),
		Apply: key.NewBinding(
			key.WithKeys("enter"),
			key.WithHelp("enter", "apply"),
		),
		Clear: key.NewBinding(
			key.WithKeys("esc"),
			key.WithHelp("esc", "clear"),
		),
		Quit: key.NewBinding(
			key.WithKeys("q", "ctrl+c"),
			key.WithHelp("q", "quit"),
		),
	}
}

type activeHelp struct {
	bindings []key.Binding
}

func (h activeHelp) ShortHelp() []key.Binding {
	return h.bindings
}

func (h activeHelp) FullHelp() [][]key.Binding {
	return [][]key.Binding{h.bindings}
}

type paneLayout struct {
	leftOuter    int
	rightOuter   int
	leftContent  int
	rightContent int
	bodyHeight   int
	paneContent  int
}

type model struct {
	data          contextPayload
	conversations list.Model
	preview       viewport.Model
	help          help.Model
	keys          keyMap
	colors        palette
	focus         paneFocus
	width         int
	height        int
}

func loadContext() (contextPayload, error) {
	backend := os.Getenv("AGENTCONVOS_BACKEND")
	if backend == "" {
		backend = "agentconvos"
	}
	cmd := exec.Command(backend, "--context", "--json")
	output, err := cmd.Output()
	if err != nil {
		return contextPayload{}, fmt.Errorf("load project context: %w", err)
	}
	var payload contextPayload
	if err := json.Unmarshal(output, &payload); err != nil {
		return contextPayload{}, fmt.Errorf("decode project context: %w", err)
	}
	if len(payload.Conversations) == 0 {
		return contextPayload{}, fmt.Errorf("no conversations found for %s", payload.Project)
	}
	return payload, nil
}

func initialModel(payload contextPayload) model {
	items := make([]list.Item, 0, len(payload.Conversations))
	for _, c := range payload.Conversations {
		items = append(items, conversationItem{conversation: c})
	}

	conversationList := list.New(items, conversationDelegate{}, 0, 0)
	conversationList.SetShowTitle(false)
	conversationList.SetShowFilter(false)
	conversationList.SetShowStatusBar(false)
	conversationList.SetShowPagination(false)
	conversationList.SetShowHelp(false)
	conversationList.SetFilteringEnabled(true)
	conversationList.DisableQuitKeybindings()
	conversationList.FilterInput.Prompt = "/ "
	conversationList.FilterInput.Placeholder = "Filter conversations"

	preview := viewport.New()
	preview.SoftWrap = true
	preview.FillHeight = true

	m := model{
		data:          payload,
		conversations: conversationList,
		preview:       preview,
		help:          help.New(),
		keys:          defaultKeyMap(),
	}
	m.applyTheme(true)
	m.refreshPreview()
	return m
}

func (m model) Init() tea.Cmd { return tea.RequestBackgroundColor }

func (m model) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	switch msg := msg.(type) {
	case tea.BackgroundColorMsg:
		m.applyTheme(msg.IsDark())
		m.refreshPreview()
		return m, nil
	case tea.WindowSizeMsg:
		m.width = msg.Width
		m.height = msg.Height
		m.resize()
		return m, nil
	case tea.KeyPressMsg:
		if m.conversations.SettingFilter() {
			before := m.selectedID()
			var cmd tea.Cmd
			m.conversations, cmd = m.conversations.Update(msg)
			if m.selectedID() != before || msg.String() == "esc" {
				m.refreshPreview()
			}
			return m, cmd
		}
		if msg.String() == "esc" && m.conversations.FilterValue() != "" {
			m.conversations.ResetFilter()
			m.refreshPreview()
			return m, nil
		}
		if key.Matches(msg, m.keys.Quit) {
			return m, tea.Quit
		}
		if key.Matches(msg, m.keys.SwitchPane) {
			if m.focus == browseFocus {
				m.focus = detailFocus
			} else {
				m.focus = browseFocus
			}
			m.applyThemeFromPalette()
			return m, nil
		}
		if key.Matches(msg, m.keys.Search) {
			m.focus = browseFocus
			m.applyThemeFromPalette()
			var cmd tea.Cmd
			m.conversations, cmd = m.conversations.Update(msg)
			return m, cmd
		}
		if m.focus == detailFocus {
			switch msg.String() {
			case "g", "home":
				m.preview.GotoTop()
				return m, nil
			case "G", "end":
				m.preview.GotoBottom()
				return m, nil
			}
			var cmd tea.Cmd
			m.preview, cmd = m.preview.Update(msg)
			return m, cmd
		}
	}

	previous := m.selectedID()
	var cmd tea.Cmd
	m.conversations, cmd = m.conversations.Update(msg)
	if m.selectedID() != previous {
		m.refreshPreview()
	}
	return m, cmd
}

func (m *model) applyTheme(isDark bool) {
	m.colors = newPalette(isDark)
	m.applyThemeFromPalette()
}

func (m *model) applyThemeFromPalette() {
	m.conversations.SetDelegate(conversationDelegate{
		colors:  m.colors,
		focused: m.focus == browseFocus,
	})

	inputStyles := m.conversations.FilterInput.Styles()
	inputStyles.Focused.Prompt = inputStyles.Focused.Prompt.Foreground(m.colors.secondary).Bold(true)
	inputStyles.Focused.Text = inputStyles.Focused.Text.Foreground(m.colors.text)
	inputStyles.Focused.Placeholder = inputStyles.Focused.Placeholder.Foreground(m.colors.muted)
	inputStyles.Focused.Suggestion = inputStyles.Focused.Suggestion.Foreground(m.colors.muted)
	inputStyles.Blurred.Prompt = inputStyles.Blurred.Prompt.Foreground(m.colors.muted)
	inputStyles.Blurred.Text = inputStyles.Blurred.Text.Foreground(m.colors.text)
	inputStyles.Blurred.Placeholder = inputStyles.Blurred.Placeholder.Foreground(m.colors.muted)
	m.conversations.FilterInput.SetStyles(inputStyles)

	m.help.Styles.ShortKey = lipgloss.NewStyle().Foreground(m.colors.primary).Bold(true)
	m.help.Styles.ShortDesc = lipgloss.NewStyle().Foreground(m.colors.muted)
	m.help.Styles.ShortSeparator = lipgloss.NewStyle().Foreground(m.colors.border)
}

func (m *model) resize() {
	layout := m.layout()
	listHeight := max(1, layout.paneContent-3)
	previewHeight := max(1, layout.paneContent-2)
	m.conversations.SetSize(layout.leftContent, listHeight)
	m.conversations.FilterInput.SetWidth(max(4, layout.leftContent-6))
	m.preview.SetWidth(layout.rightContent)
	m.preview.SetHeight(previewHeight)
	m.help.SetWidth(max(1, m.width-24))
	m.refreshPreview()
}

func (m model) layout() paneLayout {
	gap := 1
	leftOuter := max(30, min(48, m.width*36/100))
	if m.width < 100 {
		leftOuter = max(30, m.width*38/100)
	}
	leftOuter = min(leftOuter, max(1, m.width-gap-24))
	rightOuter := max(1, m.width-gap-leftOuter)
	bodyHeight := max(6, m.height-2)
	return paneLayout{
		leftOuter:    leftOuter,
		rightOuter:   rightOuter,
		leftContent:  max(1, leftOuter-4),
		rightContent: max(1, rightOuter-4),
		bodyHeight:   bodyHeight,
		paneContent:  max(1, bodyHeight-2),
	}
}

func (m *model) selectedConversation() (conversation, bool) {
	item, ok := m.conversations.SelectedItem().(conversationItem)
	if !ok {
		return conversation{}, false
	}
	return item.conversation, true
}

func (m *model) selectedID() string {
	c, ok := m.selectedConversation()
	if !ok {
		return ""
	}
	return strings.Join([]string{c.UUID, c.Source, c.Timestamp, c.FirstMessage}, "\x00")
}

func (m *model) refreshPreview() {
	c, ok := m.selectedConversation()
	if !ok {
		m.preview.SetContent(lipgloss.NewStyle().
			Foreground(m.colors.muted).
			Render("No conversations match this filter."))
		m.preview.GotoTop()
		return
	}

	title := compact(c.FirstMessage, max(8, m.preview.Width()))
	identity := strings.Join(nonEmpty(strings.ToLower(c.Source), shortID(c.UUID)), " · ")
	metadata := strings.Join(nonEmpty(date(c.Timestamp), turnLabel(c.TurnCount)), " · ")
	technical := strings.Join(nonEmpty(c.Model, c.Effort), " · ")

	parts := nonEmpty(
		lipgloss.NewStyle().Bold(true).Foreground(m.colors.text).Render(title),
		lipgloss.NewStyle().Foreground(m.colors.muted).Render(strings.Join(nonEmpty(identity, metadata), "  ")),
		lipgloss.NewStyle().Foreground(m.colors.secondary).Render(technical),
		plainSection(m.colors, "First message", c.FirstMessage),
		plainSection(m.colors, "Your latest message", c.LastUserMessage),
		plainSection(m.colors, "Agent's latest reply", c.LastAgentMessage),
	)
	m.preview.SetContent(strings.Join(parts, "\n\n"))
	m.preview.GotoTop()
}

func (m model) View() tea.View {
	if m.width == 0 || m.height == 0 {
		view := tea.NewView("Loading terminal…")
		view.AltScreen = true
		return view
	}

	layout := m.layout()
	leftBorder := m.colors.border
	rightBorder := m.colors.border
	if m.focus == browseFocus {
		leftBorder = m.colors.primary
	} else {
		rightBorder = m.colors.primary
	}
	paneStyle := func(width, height int, border color.Color) lipgloss.Style {
		return lipgloss.NewStyle().
			Width(width).
			Height(height).
			Padding(0, 1).
			BorderStyle(lipgloss.RoundedBorder()).
			BorderForeground(border).
			Background(m.colors.panel)
	}
	left := paneStyle(layout.leftContent, layout.paneContent, leftBorder).
		Render(m.listView(layout.leftContent))
	rightContent := m.paneHeading("Conversation", m.focus == detailFocus) + "\n" + m.preview.View()
	right := paneStyle(layout.rightContent, layout.paneContent, rightBorder).Render(rightContent)
	body := lipgloss.JoinHorizontal(lipgloss.Top, left, " ", right)
	canvas := lipgloss.NewStyle().
		Width(m.width).
		Height(m.height).
		Background(m.colors.canvas).
		Foreground(m.colors.text).
		Render(strings.Join([]string{m.header(), body, m.footer()}, "\n"))
	view := tea.NewView(canvas)
	view.AltScreen = true
	view.BackgroundColor = m.colors.canvas
	view.ForegroundColor = m.colors.text
	view.WindowTitle = "agentconvos · " + filepath.Base(m.data.Project)
	return view
}

func (m model) header() string {
	brand := lipgloss.NewStyle().
		Bold(true).
		Foreground(m.colors.onPrimary).
		Background(m.colors.primary).
		Padding(0, 1).
		Render("agentconvos")
	project := lipgloss.NewStyle().Bold(true).Foreground(m.colors.text).Render(filepath.Base(m.data.Project))
	left := brand + "  " + project
	right := strings.Join([]string{
		lipgloss.NewStyle().Foreground(m.colors.muted).Render(m.resultCount()),
		m.position(),
	}, "  ")
	return lipgloss.NewStyle().
		Width(m.width).
		Background(m.colors.panel).
		Render(placeSides(m.width, left, right))
}

func (m model) listView(width int) string {
	return strings.Join([]string{
		m.paneHeading("Recent", m.focus == browseFocus),
		m.searchView(width),
		m.conversations.View(),
	}, "\n")
}

func (m model) footer() string {
	bindings := []key.Binding{m.keys.Move, m.keys.Search, m.keys.SwitchPane, m.keys.Quit}
	focusLabel := "BROWSE"
	if m.conversations.SettingFilter() {
		bindings = []key.Binding{m.keys.Apply, m.keys.Clear}
		focusLabel = "FILTER"
	} else if m.focus == detailFocus {
		bindings = []key.Binding{m.keys.Scroll, m.keys.Page, m.keys.Ends, m.keys.BrowsePane, m.keys.Search, m.keys.Quit}
		focusLabel = "READING"
	}
	keys := m.help.View(activeHelp{bindings: bindings})
	right := strings.Join([]string{
		lipgloss.NewStyle().Bold(true).Foreground(m.colors.primary).Render(focusLabel),
		m.position(),
		lipgloss.NewStyle().Foreground(m.colors.secondary).Render(m.scrollState()),
	}, "  ")
	return lipgloss.NewStyle().
		Width(m.width).
		Background(m.colors.panel).
		Render(placeSides(m.width, " "+keys, right+" "))
}

func (m model) paneHeading(label string, focused bool) string {
	style := lipgloss.NewStyle().Bold(true).Foreground(m.colors.muted)
	marker := ""
	if focused {
		style = style.Foreground(m.colors.primary)
		marker = " •"
	}
	return style.Render(label + marker)
}

func (m model) searchView(width int) string {
	style := lipgloss.NewStyle().
		Width(max(1, width)).
		Foreground(m.colors.muted)
	if m.conversations.SettingFilter() || m.conversations.FilterValue() != "" {
		style = style.Background(m.colors.surface)
	}
	return style.Render(" " + m.conversations.FilterInput.View())
}

func (m model) resultCount() string {
	visible := len(m.conversations.VisibleItems())
	if m.conversations.FilterValue() != "" {
		label := "results"
		if visible == 1 {
			label = "result"
		}
		return fmt.Sprintf("%d %s of %d", visible, label, len(m.data.Conversations))
	}
	return conversationCount(len(m.data.Conversations))
}

func (m model) position() string {
	visible := len(m.conversations.VisibleItems())
	current := 0
	if visible > 0 {
		current = min(m.conversations.Index()+1, visible)
	}
	return lipgloss.NewStyle().Foreground(m.colors.text).Render(fmt.Sprintf("%d / %d", current, visible))
}

func (m model) scrollState() string {
	if m.preview.AtTop() {
		return "TOP"
	}
	if m.preview.AtBottom() {
		return "END"
	}
	return fmt.Sprintf("%d%%", int(m.preview.ScrollPercent()*100+0.5))
}

func placeSides(width int, left, right string) string {
	gap := width - lipgloss.Width(left) - lipgloss.Width(right)
	if gap < 1 {
		leftWidth := max(0, width-lipgloss.Width(right)-1)
		left = lipgloss.NewStyle().MaxWidth(leftWidth).Render(left)
		gap = max(1, width-lipgloss.Width(left)-lipgloss.Width(right))
	}
	return left + strings.Repeat(" ", gap) + right
}

func plainSection(colors palette, label, text string) string {
	if strings.TrimSpace(text) == "" {
		return ""
	}
	heading := lipgloss.NewStyle().Bold(true).Foreground(colors.muted).Render(label)
	content := lipgloss.NewStyle().Foreground(colors.text).Render(strings.TrimSpace(text))
	return heading + "\n" + content
}

func shortDate(timestamp string) string {
	months := map[string]string{
		"01": "Jan", "02": "Feb", "03": "Mar", "04": "Apr",
		"05": "May", "06": "Jun", "07": "Jul", "08": "Aug",
		"09": "Sep", "10": "Oct", "11": "Nov", "12": "Dec",
	}
	if len(timestamp) < 10 {
		return "?"
	}
	return timestamp[8:10] + " " + months[timestamp[5:7]]
}

func compact(value string, width int) string {
	value = whitespace.ReplaceAllString(strings.TrimSpace(value), " ")
	if value == "" {
		return "(no recorded prompt)"
	}
	if len([]rune(value)) <= width {
		return value
	}
	runes := []rune(value)
	return string(runes[:max(1, width-1)]) + "…"
}

func date(timestamp string) string {
	if len(timestamp) >= 10 {
		return timestamp[:10]
	}
	return ""
}

func shortID(id string) string {
	if len(id) > 8 {
		return id[:8]
	}
	return id
}

func turnLabel(turns int) string {
	if turns == 1 {
		return "1 turn"
	}
	return fmt.Sprintf("%d turns", turns)
}

func conversationCount(count int) string {
	if count == 1 {
		return "1 conversation"
	}
	return fmt.Sprintf("%d conversations", count)
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

func main() {
	payload, err := loadContext()
	if err != nil {
		fmt.Fprintln(os.Stderr, "agentconvos-tui:", err)
		os.Exit(1)
	}
	program := tea.NewProgram(initialModel(payload))
	if _, err := program.Run(); err != nil {
		fmt.Fprintln(os.Stderr, "agentconvos-tui:", err)
		os.Exit(1)
	}
}
