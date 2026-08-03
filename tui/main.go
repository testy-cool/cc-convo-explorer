package main

import (
	"encoding/json"
	"fmt"
	"image/color"
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

var whitespace = regexp.MustCompile(`\s+`)

type palette struct {
	background color.Color
	foreground color.Color
	muted      color.Color
	subtle     color.Color
	selection  color.Color
	accent     color.Color
}

func newPalette(isDark bool) palette {
	lightDark := lipgloss.LightDark(isDark)
	return palette{
		background: lightDark(lipgloss.Color("#FAF9F7"), lipgloss.Color("#151518")),
		foreground: lightDark(lipgloss.Color("#252328"), lipgloss.Color("#E8E6EA")),
		muted:      lightDark(lipgloss.Color("#77727A"), lipgloss.Color("#88838C")),
		subtle:     lightDark(lipgloss.Color("#DDD9DD"), lipgloss.Color("#343137")),
		selection:  lightDark(lipgloss.Color("#F5EDEF"), lipgloss.Color("#252126")),
		accent:     lightDark(lipgloss.Color("#B92D5D"), lipgloss.Color("#FF6B9A")),
	}
}

type keyMap struct {
	Move    key.Binding
	Preview key.Binding
	Ends    key.Binding
	Quit    key.Binding
}

func defaultKeyMap() keyMap {
	return keyMap{
		Move: key.NewBinding(
			key.WithKeys("up", "down", "j", "k"),
			key.WithHelp("↑/↓", "move"),
		),
		Preview: key.NewBinding(
			key.WithKeys("pgup", "pgdown"),
			key.WithHelp("pgup/dn", "scroll reply"),
		),
		Ends: key.NewBinding(
			key.WithKeys("home", "end", "g", "G"),
			key.WithHelp("g/G", "first/last"),
		),
		Quit: key.NewBinding(
			key.WithKeys("q", "ctrl+c"),
			key.WithHelp("q", "quit"),
		),
	}
}

func (keys keyMap) ShortHelp() []key.Binding {
	return []key.Binding{keys.Move, keys.Preview, keys.Quit}
}

func (keys keyMap) FullHelp() [][]key.Binding {
	return [][]key.Binding{{keys.Move, keys.Preview, keys.Ends, keys.Quit}}
}

type model struct {
	data          contextPayload
	conversations list.Model
	preview       viewport.Model
	help          help.Model
	keys          keyMap
	colors        palette
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

	conversationList := list.New(items, list.NewDefaultDelegate(), 0, 0)
	conversationList.SetShowTitle(false)
	conversationList.SetShowFilter(false)
	conversationList.SetShowStatusBar(false)
	conversationList.SetShowPagination(false)
	conversationList.SetShowHelp(false)
	conversationList.SetFilteringEnabled(false)
	conversationList.DisableQuitKeybindings()

	preview := viewport.New()
	preview.SoftWrap = true

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
		if key.Matches(msg, m.keys.Quit) {
			return m, tea.Quit
		}
		if key.Matches(msg, m.keys.Preview) {
			var cmd tea.Cmd
			m.preview, cmd = m.preview.Update(msg)
			return m, cmd
		}
	}

	previous := m.conversations.Index()
	var cmd tea.Cmd
	m.conversations, cmd = m.conversations.Update(msg)
	if m.conversations.Index() != previous {
		m.refreshPreview()
	}
	return m, cmd
}

func (m *model) applyTheme(isDark bool) {
	m.colors = newPalette(isDark)

	delegate := list.NewDefaultDelegate()
	delegate.SetSpacing(1)
	itemStyles := list.NewDefaultItemStyles(isDark)
	itemStyles.NormalTitle = lipgloss.NewStyle().Foreground(m.colors.foreground).PaddingLeft(2)
	itemStyles.NormalDesc = lipgloss.NewStyle().Foreground(m.colors.muted).PaddingLeft(2)
	itemStyles.SelectedTitle = lipgloss.NewStyle().
		Bold(true).
		Foreground(m.colors.foreground).
		Background(m.colors.selection).
		BorderLeft(true).
		BorderForeground(m.colors.accent).
		PaddingLeft(1)
	itemStyles.SelectedDesc = lipgloss.NewStyle().
		Foreground(m.colors.muted).
		Background(m.colors.selection).
		BorderLeft(true).
		BorderForeground(m.colors.accent).
		PaddingLeft(1)
	itemStyles.DimmedTitle = itemStyles.NormalTitle.Foreground(m.colors.muted)
	itemStyles.DimmedDesc = itemStyles.NormalDesc
	itemStyles.FilterMatch = lipgloss.NewStyle().Foreground(m.colors.accent).Underline(true)
	delegate.Styles = itemStyles
	m.conversations.SetDelegate(delegate)

	m.help.Styles = help.DefaultStyles(isDark)
	m.help.Styles.ShortKey = m.help.Styles.ShortKey.Foreground(m.colors.muted)
	m.help.Styles.ShortDesc = m.help.Styles.ShortDesc.Foreground(m.colors.muted)
	m.help.Styles.ShortSeparator = m.help.Styles.ShortSeparator.Foreground(m.colors.subtle)
}

func (m *model) resize() {
	leftWidth := max(32, min(50, m.width*38/100))
	rightWidth := max(24, m.width-leftWidth-1)
	bodyHeight := max(4, m.height-3)
	m.conversations.SetSize(max(16, leftWidth-3), max(1, bodyHeight-2))
	m.preview.SetWidth(max(12, rightWidth-5))
	m.preview.SetHeight(max(4, bodyHeight-1))
	m.help.SetWidth(max(1, m.width-10))
	m.refreshPreview()
}

func (m *model) selectedConversation() (conversation, bool) {
	item, ok := m.conversations.SelectedItem().(conversationItem)
	if !ok {
		return conversation{}, false
	}
	return item.conversation, true
}

func (m *model) refreshPreview() {
	c, ok := m.selectedConversation()
	if !ok {
		return
	}

	title := compact(c.FirstMessage, max(32, m.preview.Width()))
	identity := strings.Join(nonEmpty(strings.ToLower(c.Source), shortID(c.UUID)), " · ")
	metadata := strings.Join(nonEmpty(date(c.Timestamp), turnLabel(c.TurnCount)), " · ")
	technical := strings.Join(nonEmpty(c.Model, c.Effort), " · ")

	parts := nonEmpty(
		lipgloss.NewStyle().Bold(true).Foreground(m.colors.foreground).Render(title),
		lipgloss.NewStyle().Foreground(m.colors.muted).Render(strings.Join(nonEmpty(identity, metadata), "  ")),
		lipgloss.NewStyle().Foreground(m.colors.muted).Render(technical),
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

	leftWidth := max(32, min(50, m.width*38/100))
	rightWidth := max(24, m.width-leftWidth-1)
	bodyHeight := max(4, m.height-3)
	left := lipgloss.NewStyle().
		Width(leftWidth).
		Height(bodyHeight).
		PaddingLeft(1).
		PaddingRight(2).
		Render(m.listView(leftWidth))
	right := lipgloss.NewStyle().
		Width(rightWidth).
		Height(bodyHeight).
		PaddingLeft(2).
		BorderLeft(true).
		BorderStyle(lipgloss.NormalBorder()).
		BorderForeground(m.colors.subtle).
		Render(m.preview.View())
	body := lipgloss.JoinHorizontal(lipgloss.Top, left, right)
	canvas := lipgloss.NewStyle().
		Width(m.width).
		Height(m.height).
		Background(m.colors.background).
		Foreground(m.colors.foreground).
		Render(strings.Join([]string{m.header(), body, m.footer()}, "\n"))
	view := tea.NewView(canvas)
	view.AltScreen = true
	return view
}

func (m model) header() string {
	brand := lipgloss.NewStyle().Bold(true).Foreground(m.colors.accent).Render("agentconvos")
	project := lipgloss.NewStyle().Foreground(m.colors.muted).Render(filepath.Base(m.data.Project))
	count := lipgloss.NewStyle().Foreground(m.colors.muted).Render(conversationCount(len(m.data.Conversations)))
	left := " " + brand + "  " + project
	gap := max(1, m.width-lipgloss.Width(left)-lipgloss.Width(count)-1)
	return left + strings.Repeat(" ", gap) + count + " "
}

func (m model) listView(_ int) string {
	heading := lipgloss.NewStyle().Bold(true).Foreground(m.colors.foreground).Render("Recent")
	return heading + "\n\n" + m.conversations.View()
}

func (m model) footer() string {
	keys := m.help.View(m.keys)
	position := lipgloss.NewStyle().Foreground(m.colors.muted).Render(fmt.Sprintf(
		"%d of %d",
		m.conversations.Index()+1,
		len(m.data.Conversations),
	))
	left := " " + keys
	gap := max(1, m.width-lipgloss.Width(left)-lipgloss.Width(position)-1)
	return left + strings.Repeat(" ", gap) + position + " "
}

func plainSection(colors palette, label, text string) string {
	if strings.TrimSpace(text) == "" {
		return ""
	}
	heading := lipgloss.NewStyle().Bold(true).Foreground(colors.muted).Render(label)
	content := lipgloss.NewStyle().Foreground(colors.foreground).Render(strings.TrimSpace(text))
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
