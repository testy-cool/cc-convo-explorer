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
	"unicode"

	"charm.land/bubbles/v2/help"
	"charm.land/bubbles/v2/key"
	"charm.land/bubbles/v2/list"
	"charm.land/bubbles/v2/viewport"
	tea "charm.land/bubbletea/v2"
	"charm.land/glamour/v2"
	"charm.land/glamour/v2/styles"
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
	return conversationTitle(item.conversation)
}

func (item conversationItem) Description() string {
	c := item.conversation
	return strings.Join(nonEmpty(
		strings.ToLower(c.Source),
		turnLabel(c.TurnCount),
		shortDate(c.Timestamp),
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
func (d conversationDelegate) Spacing() int { return 0 }
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
	textWidth := max(1, rowWidth-2)
	marker := "· "
	if selected {
		marker = "● "
	}

	titleStyle := lipgloss.NewStyle().
		Width(rowWidth).
		Foreground(d.colors.text).
		Background(d.colors.feed)
	metaStyle := lipgloss.NewStyle().
		Width(rowWidth).
		Foreground(d.colors.muted).
		Background(d.colors.feed)
	if selected {
		selection := d.colors.selectionInactive
		if d.focused {
			selection = d.colors.selection
			titleStyle = titleStyle.Foreground(d.colors.signature)
		}
		titleStyle = titleStyle.Bold(true).Background(selection)
		metaStyle = metaStyle.Background(selection)
	}

	title := marker + truncateCells(item.Title(), textWidth)
	c := item.conversation
	metaLeft := strings.Join(nonEmpty(strings.ToLower(c.Source), turnLabel(c.TurnCount)), " · ")
	metadata := "  " + placeSides(textWidth, metaLeft, shortDate(c.Timestamp))
	lines := []string{titleStyle.Render(title), metaStyle.Render(metadata)}
	_, _ = io.WriteString(w, strings.Join(lines, "\n"))
}

var whitespace = regexp.MustCompile(`\s+`)
var markdownDecoration = regexp.MustCompile("[*`~]")
var markdownLink = regexp.MustCompile(`\[([^]]+)]\([^)]+\)`)

type palette struct {
	canvas            color.Color
	feed              color.Color
	paper             color.Color
	raised            color.Color
	text              color.Color
	muted             color.Color
	faint             color.Color
	separator         color.Color
	signature         color.Color
	question          color.Color
	answer            color.Color
	selection         color.Color
	selectionInactive color.Color
	match             color.Color
	status            color.Color
}

func newPalette(isDark bool) palette {
	lightDark := lipgloss.LightDark(isDark)
	return palette{
		canvas:            lightDark(lipgloss.Color("#F5F0E7"), lipgloss.Color("#101211")),
		feed:              lightDark(lipgloss.Color("#EDE7DC"), lipgloss.Color("#171918")),
		paper:             lightDark(lipgloss.Color("#FFF9ED"), lipgloss.Color("#211F1A")),
		raised:            lightDark(lipgloss.Color("#F3E7D5"), lipgloss.Color("#2B2720")),
		text:              lightDark(lipgloss.Color("#29251F"), lipgloss.Color("#F2E8D5")),
		muted:             lightDark(lipgloss.Color("#736B60"), lipgloss.Color("#A59B8C")),
		faint:             lightDark(lipgloss.Color("#958C7E"), lipgloss.Color("#6F6A60")),
		separator:         lightDark(lipgloss.Color("#D5C8B5"), lipgloss.Color("#3A3832")),
		signature:         lightDark(lipgloss.Color("#C6472C"), lipgloss.Color("#FF6B4A")),
		question:          lightDark(lipgloss.Color("#347D72"), lipgloss.Color("#70B7A8")),
		answer:            lightDark(lipgloss.Color("#9B6B19"), lipgloss.Color("#D7A84A")),
		selection:         lightDark(lipgloss.Color("#F0D6C9"), lipgloss.Color("#38251F")),
		selectionInactive: lightDark(lipgloss.Color("#E5DED2"), lipgloss.Color("#292621")),
		match:             lightDark(lipgloss.Color("#8B681F"), lipgloss.Color("#E4BD69")),
		status:            lightDark(lipgloss.Color("#4F765D"), lipgloss.Color("#91B59A")),
	}
}

const (
	minimumWidth  = 72
	minimumHeight = 18
)

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
			key.WithHelp("↑/↓ j/k", "move"),
		),
		Scroll: key.NewBinding(
			key.WithKeys("up", "down", "j", "k"),
			key.WithHelp("↑/↓ j/k", "scroll"),
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
			key.WithKeys("tab", "shift+tab"),
			key.WithHelp("tab", "read"),
		),
		BrowsePane: key.NewBinding(
			key.WithKeys("tab", "shift+tab"),
			key.WithHelp("tab", "browse"),
		),
		Search: key.NewBinding(
			key.WithKeys("/"),
			key.WithHelp("/", "search"),
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
			key.WithKeys("ctrl+c"),
			key.WithHelp("ctrl+c", "quit"),
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
	compact      bool
	headerHeight int
	searchHeight int
	footerHeight int
	gutter       int
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
	isDark        bool
	width         int
	height        int
	filterAnchor  string
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
	conversationList.FilterInput.Prompt = ""
	conversationList.FilterInput.Placeholder = "type to filter…"
	conversationList.FilterInput.SetVirtualCursor(false)

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
		atBottom, scrollPercent, preserve := m.previewPosition()
		m.applyTheme(msg.IsDark())
		m.refreshPreview()
		m.restorePreviewPosition(atBottom, scrollPercent, preserve)
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
		if m.conversations.SettingFilter() {
			before := m.selectedID()
			var cmd tea.Cmd
			m.conversations, cmd = m.conversations.Update(msg)
			if msg.String() == "esc" {
				m.restoreFilterSelection()
				m.filterAnchor = ""
			}
			if m.selectedID() != before || msg.String() == "esc" {
				m.refreshPreview()
			}
			if msg.String() == "esc" || msg.String() == "enter" {
				m.resize()
			}
			return m, cmd
		}
		if msg.String() == "esc" && m.conversations.FilterValue() != "" {
			m.conversations.ResetFilter()
			m.restoreFilterSelection()
			m.filterAnchor = ""
			m.refreshPreview()
			return m, nil
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
			if m.filterAnchor == "" {
				m.filterAnchor = m.selectedID()
			}
			m.focus = browseFocus
			m.applyThemeFromPalette()
			var cmd tea.Cmd
			m.conversations, cmd = m.conversations.Update(msg)
			m.resize()
			return m, cmd
		}
		if msg.String() == "esc" && m.layout().compact && m.focus == detailFocus {
			m.focus = browseFocus
			m.applyThemeFromPalette()
			return m, nil
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
	_, filterResultsUpdated := msg.(list.FilterMatchesMsg)
	var cmd tea.Cmd
	m.conversations, cmd = m.conversations.Update(msg)
	if filterResultsUpdated {
		m.restoreFilterSelection()
	}
	if m.selectedID() != previous {
		m.refreshPreview()
	}
	return m, cmd
}

func (m *model) applyTheme(isDark bool) {
	m.isDark = isDark
	m.colors = newPalette(isDark)
	m.applyThemeFromPalette()
}

func (m *model) applyThemeFromPalette() {
	m.conversations.SetDelegate(conversationDelegate{
		colors:  m.colors,
		focused: m.focus == browseFocus,
	})
	m.conversations.Styles.DefaultFilterCharacterMatch = lipgloss.NewStyle().
		Foreground(m.colors.match).
		Underline(true)

	inputStyles := m.conversations.FilterInput.Styles()
	inputStyles.Cursor.Color = m.colors.signature
	inputStyles.Focused.Prompt = inputStyles.Focused.Prompt.Foreground(m.colors.match).Bold(true)
	inputStyles.Focused.Text = inputStyles.Focused.Text.Foreground(m.colors.text)
	inputStyles.Focused.Placeholder = inputStyles.Focused.Placeholder.Foreground(m.colors.muted)
	inputStyles.Focused.Suggestion = inputStyles.Focused.Suggestion.Foreground(m.colors.muted)
	inputStyles.Blurred.Prompt = inputStyles.Blurred.Prompt.Foreground(m.colors.muted)
	inputStyles.Blurred.Text = inputStyles.Blurred.Text.Foreground(m.colors.text)
	inputStyles.Blurred.Placeholder = inputStyles.Blurred.Placeholder.Foreground(m.colors.muted)
	m.conversations.FilterInput.SetStyles(inputStyles)

	m.help.Styles.ShortKey = lipgloss.NewStyle().Foreground(m.colors.signature).Bold(true)
	m.help.Styles.ShortDesc = lipgloss.NewStyle().Foreground(m.colors.muted)
	m.help.Styles.ShortSeparator = lipgloss.NewStyle().Foreground(m.colors.separator)
}

func (m *model) resize() {
	atBottom, scrollPercent, preserve := m.previewPosition()
	layout := m.layout()
	listHeight := max(1, layout.paneContent-1)
	if m.showCompactSpotlight() {
		listHeight = max(1, len(m.conversations.VisibleItems())*(conversationDelegate{}).Height())
	}
	previewHeight := max(1, layout.paneContent)
	m.conversations.SetSize(layout.leftContent, listHeight)
	searchChrome := lipgloss.Width(m.searchPrefix()) + 24
	m.conversations.FilterInput.SetWidth(max(8, m.width-searchChrome))
	m.preview.SetWidth(layout.rightContent)
	m.preview.SetHeight(previewHeight)
	m.help.SetWidth(max(1, m.width-30))
	m.refreshPreview()
	m.restorePreviewPosition(atBottom, scrollPercent, preserve)
}

func (m model) layout() paneLayout {
	headerHeight := 2
	footerHeight := 1
	searchHeight := 0
	if m.conversations.SettingFilter() {
		searchHeight = 1
	}
	compactMode := m.width < 100
	gap := 2
	leftOuter := 37
	if m.width >= 140 {
		gap = 3
		leftOuter = 42
	} else if m.width >= 120 {
		leftOuter = 40
	}
	if compactMode {
		gap = 0
		leftOuter = m.width
	}
	leftOuter = min(leftOuter, max(1, m.width-gap-42))
	if compactMode {
		leftOuter = m.width
	}
	rightOuter := max(1, m.width-gap-leftOuter)
	if compactMode {
		rightOuter = m.width
	}
	rightInset := 2
	bodyHeight := max(1, m.height-headerHeight-searchHeight-footerHeight)
	return paneLayout{
		compact:      compactMode,
		headerHeight: headerHeight,
		searchHeight: searchHeight,
		footerHeight: footerHeight,
		gutter:       gap,
		leftOuter:    leftOuter,
		rightOuter:   rightOuter,
		leftContent:  leftOuter,
		rightContent: max(1, rightOuter-rightInset*2),
		bodyHeight:   bodyHeight,
		paneContent:  bodyHeight,
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
	return conversationID(c)
}

func conversationID(c conversation) string {
	return strings.Join([]string{c.UUID, c.Source, c.Timestamp, c.FirstMessage}, "\x00")
}

func (m *model) restoreFilterSelection() {
	if m.filterAnchor == "" {
		return
	}
	for index, raw := range m.conversations.VisibleItems() {
		item, ok := raw.(conversationItem)
		if ok && conversationID(item.conversation) == m.filterAnchor {
			m.conversations.Select(index)
			return
		}
	}
}

func (m model) previewPosition() (atBottom bool, scrollPercent float64, preserve bool) {
	preserve = m.preview.Width() > 0 && m.preview.Height() > 0 && m.preview.TotalLineCount() > 0
	if !preserve {
		return false, 0, false
	}
	return m.preview.AtBottom(), m.preview.ScrollPercent(), true
}

func (m *model) restorePreviewPosition(atBottom bool, scrollPercent float64, preserve bool) {
	if !preserve {
		return
	}
	if atBottom {
		m.preview.GotoBottom()
		return
	}
	maxOffset := max(0, m.preview.TotalLineCount()-m.preview.Height())
	m.preview.SetYOffset(int(float64(maxOffset)*scrollPercent + 0.5))
}

func (m model) tooSmall() bool {
	return m.width < minimumWidth || m.height < minimumHeight
}

func (m *model) refreshPreview() {
	c, ok := m.selectedConversation()
	if !ok {
		query := strings.TrimSpace(m.conversations.FilterValue())
		message := "No conversations are available."
		if query != "" {
			message = fmt.Sprintf("No conversations match %q.\n\nEsc clears the filter.", query)
		}
		m.preview.SetContent(lipgloss.NewStyle().
			Foreground(m.colors.muted).
			Render(message))
		m.preview.GotoTop()
		return
	}

	title := readingTitle(c)
	metadata := strings.Join(nonEmpty(
		editorialDate(c.Timestamp),
		strings.ToLower(c.Source),
		turnLabel(c.TurnCount),
		shortID(c.UUID),
	), " · ")
	technical := strings.Join(nonEmpty(c.Model, c.Effort), " · ")
	firstMessage := c.FirstMessage
	latestUser := c.LastUserMessage
	if strings.TrimSpace(latestUser) == strings.TrimSpace(c.FirstMessage) {
		latestUser = ""
	}
	delegated := isDelegatedTask(c.FirstMessage)
	heroSpeaker := "You asked"
	if delegated {
		heroSpeaker = "Task opened"
		firstMessage = ""
	} else if titleCarriesOpening(title, firstMessage, max(8, m.preview.Width()-2)) {
		firstMessage = ""
	}

	parts := nonEmpty(
		m.readingHeader(heroSpeaker, title, metadata, technical, latestOutcome(c)),
		m.timelineSection("You opened with", firstMessage, m.colors.question),
		m.timelineSection("You asked next", latestUser, m.colors.question),
		m.timelineSection("Agent answered", c.LastAgentMessage, m.colors.answer),
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
	if m.tooSmall() {
		return m.tooSmallView()
	}

	layout := m.layout()
	var body string
	if layout.compact {
		if m.focus == browseFocus {
			body = lipgloss.NewStyle().
				Width(m.width).
				Height(layout.bodyHeight).
				Background(m.colors.feed).
				Render(m.listView(m.width))
		} else {
			body = lipgloss.NewStyle().
				Width(m.width).
				Height(layout.bodyHeight).
				PaddingLeft(2).
				PaddingRight(2).
				Background(m.colors.paper).
				Render(m.preview.View())
		}
	} else {
		left := lipgloss.NewStyle().
			Width(layout.leftOuter).
			Height(layout.bodyHeight).
			Background(m.colors.feed).
			Render(m.listView(layout.leftContent))
		gutter := lipgloss.NewStyle().
			Width(layout.gutter).
			Height(layout.bodyHeight).
			Background(m.colors.canvas).
			Render("")
		right := lipgloss.NewStyle().
			Width(layout.rightOuter).
			Height(layout.bodyHeight).
			PaddingLeft(2).
			PaddingRight(2).
			Background(m.colors.paper).
			Render(m.preview.View())
		body = lipgloss.JoinHorizontal(lipgloss.Top, left, gutter, right)
	}
	rows := []string{m.header()}
	if m.conversations.SettingFilter() {
		rows = append(rows, m.searchView(m.width))
	}
	rows = append(rows, body, m.footer())
	canvas := lipgloss.NewStyle().
		Width(m.width).
		Height(m.height).
		Background(m.colors.canvas).
		Foreground(m.colors.text).
		Render(strings.Join(rows, "\n"))
	view := tea.NewView(canvas)
	view.AltScreen = true
	view.BackgroundColor = m.colors.canvas
	view.ForegroundColor = m.colors.text
	view.WindowTitle = "agentconvos · " + filepath.Base(m.data.Project)
	if m.conversations.SettingFilter() {
		if cursor := m.conversations.FilterInput.Cursor(); cursor != nil {
			adjusted := *cursor
			adjusted.X += lipgloss.Width(m.searchPrefix())
			adjusted.Y += layout.headerHeight
			view.Cursor = &adjusted
		}
	}
	return view
}

func (m model) tooSmallView() tea.View {
	title := lipgloss.NewStyle().Bold(true).Foreground(m.colors.signature).Render("AgentConvos")
	dimensions := lipgloss.NewStyle().Foreground(m.colors.text).Render(
		fmt.Sprintf("needs at least %dx%d · current %dx%d", minimumWidth, minimumHeight, m.width, m.height),
	)
	hint := lipgloss.NewStyle().Foreground(m.colors.muted).Render("Resize the terminal to browse conversations")
	content := strings.Join([]string{title, "", dimensions, hint}, "\n")
	canvas := lipgloss.NewStyle().
		Width(m.width).
		Height(m.height).
		Align(lipgloss.Center).
		AlignVertical(lipgloss.Center).
		Background(m.colors.canvas).
		Foreground(m.colors.text).
		Render(content)
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
		Foreground(m.colors.signature).
		Render("agentconvos")
	journal := lipgloss.NewStyle().Bold(true).Foreground(m.colors.answer).Render("FIELD NOTES")
	firstLeft := " " + brand + "  " + journal
	firstRight := lipgloss.NewStyle().Foreground(m.colors.muted).Render(m.resultCount()) + " "
	first := lipgloss.NewStyle().
		Width(m.width).
		Background(m.colors.canvas).
		Render(placeSides(m.width, firstLeft, firstRight))

	project := lipgloss.NewStyle().Bold(true).Foreground(m.colors.text).Render(filepath.Base(m.data.Project))
	secondLeft := " " + project
	secondRight := ""
	query := strings.TrimSpace(m.conversations.FilterValue())
	if m.conversations.SettingFilter() {
		secondRight = lipgloss.NewStyle().Bold(true).Foreground(m.colors.signature).Render("SEARCH") + "  " + m.position() + "  "
	} else if query != "" {
		filter := lipgloss.NewStyle().Bold(true).Foreground(m.colors.match).Render("FILTER")
		secondRight = filter + " " + lipgloss.NewStyle().Foreground(m.colors.text).Render(query) + "  " +
			lipgloss.NewStyle().Foreground(m.colors.status).Render(m.resultCount()) + "  "
	} else {
		focus := "BROWSE"
		if m.focus == detailFocus {
			focus = "READ"
		}
		secondRight = lipgloss.NewStyle().Foreground(m.colors.faint).Render(focus) + "  " +
			m.position() + "  " + lipgloss.NewStyle().Foreground(m.colors.muted).Render("/ search") + " "
	}
	second := lipgloss.NewStyle().
		Width(m.width).
		Background(m.colors.canvas).
		Render(placeSides(m.width, secondLeft, secondRight))
	return first + "\n" + second
}

func (m model) listView(width int) string {
	marker := lipgloss.NewStyle().Foreground(m.colors.faint).Render("○")
	headingStyle := lipgloss.NewStyle().Bold(true).Foreground(m.colors.muted)
	if m.focus == browseFocus {
		marker = lipgloss.NewStyle().Foreground(m.colors.signature).Render("●")
		headingStyle = headingStyle.Foreground(m.colors.text)
	}
	heading := lipgloss.NewStyle().
		Width(max(1, width)).
		Background(m.colors.feed).
		Render(" " + marker + "  " + headingStyle.Render("RECENT NOTES"))
	if len(m.conversations.VisibleItems()) == 0 {
		query := strings.TrimSpace(m.conversations.FilterValue())
		message := "No recent notes are available."
		if query != "" {
			message = fmt.Sprintf("No conversations match %q.\n\nEsc clears the filter.", query)
		}
		empty := lipgloss.NewStyle().
			Width(max(1, width)).
			PaddingLeft(4).
			PaddingTop(1).
			Foreground(m.colors.muted).
			Background(m.colors.feed).
			Render(message)
		return heading + "\n" + empty
	}
	parts := []string{heading, m.conversations.View()}
	if m.showCompactSpotlight() {
		parts = append(parts, "", m.compactSpotlight(width))
	}
	return strings.Join(parts, "\n")
}

func (m model) showCompactSpotlight() bool {
	layout := m.layout()
	if !layout.compact || m.focus != browseFocus || m.conversations.SettingFilter() {
		return false
	}
	visible := len(m.conversations.VisibleItems())
	if visible == 0 {
		return false
	}
	c, ok := m.selectedConversation()
	if !ok || firstTextLine(latestOutcome(c)) == "" {
		return false
	}
	entryRows := visible * (conversationDelegate{}).Height()
	return entryRows+7 <= layout.paneContent-1
}

func (m model) compactSpotlight(width int) string {
	c, ok := m.selectedConversation()
	if !ok {
		return ""
	}
	outcome := firstTextLine(latestOutcome(c))
	if outcome == "" {
		return ""
	}
	label := lipgloss.NewStyle().Bold(true).Foreground(m.colors.answer).Render("ON THIS NOTE")
	ruleWidth := max(0, width-lipgloss.Width("  ON THIS NOTE  ")-2)
	rule := lipgloss.NewStyle().Foreground(m.colors.separator).Render(strings.Repeat("─", ruleWidth))
	heading := "  " + label
	if ruleWidth > 0 {
		heading += "  " + rule
	}
	body := strings.Join(wrappedLines(outcome, max(1, width-6), 3), "\n")
	body = lipgloss.NewStyle().PaddingLeft(4).Foreground(m.colors.text).Render(body)
	return heading + "\n" + body
}

func (m model) footer() string {
	bindings := []key.Binding{m.keys.Move, m.keys.Search, m.keys.SwitchPane, m.keys.Quit}
	focusLabel := "BROWSE"
	if m.conversations.SettingFilter() {
		bindings = []key.Binding{m.keys.Apply, m.keys.Clear}
		focusLabel = "SEARCH"
	} else if m.focus == detailFocus {
		bindings = []key.Binding{m.keys.Scroll, m.keys.Page, m.keys.Ends, m.keys.BrowsePane, m.keys.Search, m.keys.Quit}
		if m.layout().compact {
			bindings = []key.Binding{m.keys.Scroll, m.keys.Page, m.keys.BrowsePane, m.keys.Quit}
		}
		focusLabel = "READ"
	}
	keys := m.help.View(activeHelp{bindings: bindings})
	state := ""
	if !m.conversations.SettingFilter() && m.focus == detailFocus {
		state = m.position() + "  " + lipgloss.NewStyle().Foreground(m.colors.status).Render(m.scrollState())
	}
	right := lipgloss.NewStyle().Bold(true).Foreground(m.colors.signature).Render(focusLabel)
	if state != "" {
		right += "  " + state
	}
	return lipgloss.NewStyle().
		Width(m.width).
		Background(m.colors.feed).
		Render(placeSides(m.width, " "+keys, right+" "))
}

func (m model) searchPrefix() string {
	return "  SEARCH FIELD NOTES  "
}

func (m model) searchView(width int) string {
	label := lipgloss.NewStyle().Bold(true).Foreground(m.colors.signature).Render(m.searchPrefix())
	left := label + m.conversations.FilterInput.View()
	right := lipgloss.NewStyle().Foreground(m.colors.status).Render(m.resultCount()) +
		lipgloss.NewStyle().Foreground(m.colors.muted).Render("  Esc clear  ")
	return lipgloss.NewStyle().
		Width(max(1, width)).
		Background(m.colors.raised).
		Render(placeSides(width, left, right))
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
	return lipgloss.NewStyle().Foreground(m.colors.text).Render(m.positionText())
}

func (m model) positionText() string {
	visible := len(m.conversations.VisibleItems())
	current := 0
	if visible > 0 {
		current = min(m.conversations.Index()+1, visible)
	}
	return fmt.Sprintf("%d / %d", current, visible)
}

func (m model) scrollState() string {
	if m.preview.AtTop() && m.preview.AtBottom() {
		return "ALL"
	}
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

func (m model) timelineSection(label, text string, tone color.Color) string {
	if strings.TrimSpace(text) == "" {
		return ""
	}
	headingStyle := lipgloss.NewStyle().Bold(true).Foreground(tone)
	heading := "  " + headingStyle.Render("●  "+label)
	ruleWidth := max(0, m.preview.Width()-lipgloss.Width("  ●  "+label)-2)
	if ruleWidth > 0 {
		rule := lipgloss.NewStyle().Foreground(m.colors.separator).Render(strings.Repeat("─", ruleWidth))
		heading += "  " + rule
	}
	content := lipgloss.NewStyle().PaddingLeft(3).Render(m.renderMarkdown(text))
	return heading + "\n" + content
}

func (m model) readingHeader(speaker, title, metadata, technical, outcome string) string {
	width := max(1, m.preview.Width())
	contentWidth := max(1, width-2)
	background := m.colors.raised
	eyebrowStyle := lipgloss.NewStyle().Bold(true).Foreground(m.colors.signature).Background(background)
	speakerStyle := lipgloss.NewStyle().Bold(true).Foreground(m.colors.question).Background(background)
	titleStyle := lipgloss.NewStyle().
		Bold(true).
		Foreground(m.colors.text).
		Background(background)
	metaStyle := lipgloss.NewStyle().
		Foreground(m.colors.muted).
		Background(background)
	technicalStyle := lipgloss.NewStyle().
		Foreground(m.colors.answer).
		Background(background)

	eyebrow := eyebrowStyle.Render("FIELD NOTE "+m.positionText()) + "  " + speakerStyle.Render(speaker)
	titleLines := lipgloss.Wrap(strings.TrimSpace(title), contentWidth, " -_/")
	lines := []string{eyebrow, titleStyle.Render(titleLines)}
	if metadata != "" {
		lines = append(lines, metaStyle.Render(metadata))
	}
	if technical != "" {
		lines = append(lines, technicalStyle.Render(technical))
	}
	if strings.TrimSpace(outcome) != "" {
		outcomeLabel := lipgloss.NewStyle().Bold(true).Foreground(m.colors.answer).Background(background).Render("Latest outcome")
		outcomeBody := lipgloss.NewStyle().Foreground(m.colors.text).Background(background).Render(m.renderMarkdown(outcome))
		lines = append(lines, "", outcomeLabel, outcomeBody)
	}
	return lipgloss.NewStyle().
		Width(width).
		PaddingLeft(1).
		PaddingRight(1).
		Background(background).
		Render(strings.Join(lines, "\n"))
}

func (m model) renderMarkdown(markdown string) string {
	style := styles.DarkStyleConfig
	if !m.isDark {
		style = styles.LightStyleConfig
	}

	zero := uint(0)
	text := terminalColor(m.colors.text)
	muted := terminalColor(m.colors.muted)
	accent := terminalColor(m.colors.signature)
	match := terminalColor(m.colors.match)
	raised := terminalColor(m.colors.raised)
	style.Document.Margin = &zero
	style.Document.Color = &text
	style.Paragraph.Color = &text
	style.Text.Color = &text
	style.Heading.Color = &accent
	style.H1.Color = &accent
	style.H2.Color = &accent
	style.H3.Color = &accent
	style.H4.Color = &accent
	style.H5.Color = &accent
	style.H6.Color = &accent
	style.H1.BlockPrefix = ""
	style.H1.Prefix = ""
	style.H2.BlockPrefix = ""
	style.H2.Prefix = ""
	style.H3.BlockPrefix = ""
	style.H3.Prefix = ""
	style.H4.BlockPrefix = ""
	style.H4.Prefix = ""
	style.H5.BlockPrefix = ""
	style.H5.Prefix = ""
	style.H6.BlockPrefix = ""
	style.H6.Prefix = ""
	style.Strong.Color = &match
	style.Emph.Color = &match
	style.Link.Color = &accent
	style.LinkText.Color = &accent
	style.Code.Color = &match
	style.Code.BackgroundColor = &raised
	style.BlockQuote.Color = &muted
	style.Item.Color = &text
	style.Enumeration.Color = &accent

	renderer, err := glamour.NewTermRenderer(
		glamour.WithStyles(style),
		glamour.WithWordWrap(max(12, m.preview.Width()-4)),
		glamour.WithPreservedNewLines(),
	)
	if err != nil {
		return lipgloss.NewStyle().Foreground(m.colors.text).Render(strings.TrimSpace(markdown))
	}
	rendered, err := renderer.Render(markdown)
	if err != nil {
		return lipgloss.NewStyle().Foreground(m.colors.text).Render(strings.TrimSpace(markdown))
	}
	return strings.Trim(rendered, "\n")
}

func terminalColor(value color.Color) string {
	r, g, b, _ := value.RGBA()
	return fmt.Sprintf("#%02X%02X%02X", uint8(r>>8), uint8(g>>8), uint8(b>>8))
}

func conversationTitle(c conversation) string {
	for _, candidate := range []string{c.Slug, c.Summary, c.FirstMessage} {
		if title := firstTextLine(candidate); title != "" {
			return humanizeTitle(title)
		}
	}
	return "No recorded prompt"
}

func readingTitle(c conversation) string {
	return conversationTitle(c)
}

func latestOutcome(c conversation) string {
	if summary := strings.TrimSpace(c.Summary); summary != "" {
		return summary
	}
	return firstParagraph(c.LastAgentMessage)
}

func firstParagraph(value string) string {
	value = strings.ReplaceAll(value, "\r\n", "\n")
	value = strings.TrimSpace(value)
	if value == "" {
		return ""
	}
	for _, paragraph := range strings.Split(value, "\n\n") {
		if paragraph = strings.TrimSpace(paragraph); paragraph != "" {
			for _, line := range strings.Split(paragraph, "\n") {
				if line = strings.TrimSpace(line); line != "" {
					return line
				}
			}
		}
	}
	return ""
}

func isDelegatedTask(value string) bool {
	return strings.HasPrefix(strings.ToLower(strings.TrimSpace(value)), "[delegated task]")
}

func firstTextLine(value string) string {
	for _, line := range strings.Split(value, "\n") {
		line = strings.TrimSpace(line)
		if line == "" {
			continue
		}
		line = strings.TrimSpace(strings.TrimLeft(line, "#"))
		line = markdownLink.ReplaceAllString(line, "$1")
		line = markdownDecoration.ReplaceAllString(line, "")
		return whitespace.ReplaceAllString(line, " ")
	}
	return ""
}

func humanizeTitle(value string) string {
	value = strings.TrimSpace(value)
	lower := strings.ToLower(value)
	delegated := false
	if strings.HasPrefix(lower, "[delegated task]") {
		delegated = true
		value = strings.TrimSpace(value[len("[delegated task]"):])
	}
	lower = strings.ToLower(value)
	if strings.HasSuffix(lower, "(prompt not recorded)") {
		value = strings.TrimSpace(value[:len(value)-len("(prompt not recorded)")])
	}
	if delegated {
		value = strings.ReplaceAll(value, "_", " ")
	} else {
		value = strings.Trim(value, "_")
	}
	value = whitespace.ReplaceAllString(value, " ")
	words := strings.Fields(value)
	acronyms := map[string]string{
		"api": "API", "cli": "CLI", "json": "JSON", "readme": "README",
		"sdk": "SDK", "ssh": "SSH", "tui": "TUI", "ui": "UI", "url": "URL",
	}
	for index, word := range words {
		if acronym, ok := acronyms[strings.ToLower(word)]; ok {
			words[index] = acronym
		}
	}
	value = strings.Join(words, " ")
	if value == "" {
		return "No recorded prompt"
	}
	runes := []rune(value)
	runes[0] = unicode.ToUpper(runes[0])
	return string(runes)
}

func titleCarriesOpening(title, opening string, width int) bool {
	opening = strings.TrimSpace(opening)
	if opening == "" || strings.Contains(opening, "\n") {
		return false
	}
	plain := firstTextLine(opening)
	if plain != title {
		return false
	}
	return len(wrappedLines(title, width, 3)) <= 2
}

func wrappedLines(value string, width, limit int) []string {
	value = whitespace.ReplaceAllString(strings.TrimSpace(value), " ")
	if value == "" {
		return []string{"No recorded prompt"}
	}
	width = max(1, width)
	lines := strings.Split(lipgloss.Wrap(value, width, " -_/"), "\n")
	truncated := len(lines) > limit
	if truncated {
		lines = lines[:limit]
	}
	for index, line := range lines {
		lines[index] = truncateCells(strings.TrimSpace(line), width)
	}
	if truncated && len(lines) > 0 {
		last := len(lines) - 1
		lines[last] = strings.TrimRight(truncateCells(lines[last], max(1, width-1)), "… ") + "…"
	}
	return lines
}

func truncateCells(value string, width int) string {
	width = max(1, width)
	if lipgloss.Width(value) <= width {
		return value
	}
	runes := []rune(value)
	for len(runes) > 0 && lipgloss.Width(string(runes)+"…") > width {
		runes = runes[:len(runes)-1]
	}
	return strings.TrimRight(string(runes), " ") + "…"
}

func shortDate(timestamp string) string {
	months := map[string]string{
		"01": "Jan", "02": "Feb", "03": "Mar", "04": "Apr",
		"05": "May", "06": "Jun", "07": "Jul", "08": "Aug",
		"09": "Sep", "10": "Oct", "11": "Nov", "12": "Dec",
	}
	if len(timestamp) < 10 {
		return ""
	}
	month, ok := months[timestamp[5:7]]
	if !ok {
		return ""
	}
	return timestamp[8:10] + " " + month
}

func editorialDate(timestamp string) string {
	short := shortDate(timestamp)
	if short == "" || len(timestamp) < 4 {
		return ""
	}
	return short + " " + timestamp[:4]
}

func compact(value string, width int) string {
	value = whitespace.ReplaceAllString(strings.TrimSpace(value), " ")
	if value == "" {
		return "No recorded prompt"
	}
	return truncateCells(value, width)
}

func shortID(id string) string {
	if len(id) > 8 {
		return id[:8]
	}
	return id
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
