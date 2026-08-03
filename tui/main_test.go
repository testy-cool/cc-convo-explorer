package main

import (
	"regexp"
	"strings"
	"testing"

	"charm.land/bubbles/v2/list"
	tea "charm.land/bubbletea/v2"
	"charm.land/lipgloss/v2"
)

var ansiSequence = regexp.MustCompile(`\x1b\[[0-9;:]*m`)

func press(m model, code rune, text string) model {
	updated, _ := m.Update(tea.KeyPressMsg{Code: code, Text: text})
	return updated.(model)
}

func pressKey(m model, msg tea.KeyPressMsg) (model, tea.Cmd) {
	updated, cmd := m.Update(msg)
	return updated.(model), cmd
}

func sizedModel(payload contextPayload, width, height int) model {
	m := initialModel(payload)
	m.width = width
	m.height = height
	m.resize()
	return m
}

func TestHeaderKeepsProjectContextQuiet(t *testing.T) {
	m := initialModel(contextPayload{
		Project: "/work/convo-explorer",
		Conversations: []conversation{
			{UUID: "one", Source: "codex"},
			{UUID: "two", Source: "claude"},
		},
	})
	m.width = 110

	header := ansiSequence.ReplaceAllString(m.header(), "")
	for _, wanted := range []string{"agentconvos", "convo-explorer", "2 conversations"} {
		if !strings.Contains(header, wanted) {
			t.Fatalf("expected quiet project context %q in header:\n%s", wanted, header)
		}
	}
	for _, noisy := range []string{"SIGNAL DECK", "LIVE", "FEEDS"} {
		if strings.Contains(header, noisy) {
			t.Fatalf("expected header without cyber-console label %q:\n%s", noisy, header)
		}
	}
}

func TestConversationListPrioritizesContentOverChrome(t *testing.T) {
	m := initialModel(contextPayload{
		Project: "/work/convo-explorer",
		Conversations: []conversation{
			{
				UUID:         "019fc465-4e56-7e61-9f93-aac628fd0594",
				Source:       "codex",
				Timestamp:    "2026-08-02T21:33:21Z",
				TurnCount:    5,
				FirstMessage: "Build the polished public README",
			},
		},
	})
	m.width = 120
	m.height = 12
	m.resize()

	list := ansiSequence.ReplaceAllString(m.listView(52), "")
	for _, wanted := range []string{"Recent conversations", "Build the polished public README", "codex · 02 Aug · 5 turns"} {
		if !strings.Contains(list, wanted) {
			t.Fatalf("expected content-first list detail %q:\n%s", wanted, list)
		}
	}
	for _, noisy := range []string{"TRANSMISSIONS", "◆", "◇"} {
		if strings.Contains(list, noisy) {
			t.Fatalf("expected list without decorative marker %q:\n%s", noisy, list)
		}
	}
}

func TestConversationListHumanizesAndWrapsDelegatedTaskTitles(t *testing.T) {
	m := sizedModel(contextPayload{
		Project: "/work/convo-explorer",
		Conversations: []conversation{{
			UUID:         "one",
			Source:       "codex",
			Timestamp:    "2026-08-02T21:33:21Z",
			TurnCount:    6,
			FirstMessage: "[delegated task] readme_green_cli (prompt not recorded)",
		}},
	}, 90, 30)

	item := m.conversations.SelectedItem()
	var rendered strings.Builder
	delegate := conversationDelegate{colors: m.colors, focused: true}
	delegate.Render(&rendered, m.conversations, 0, item)
	plain := ansiSequence.ReplaceAllString(rendered.String(), "")

	if got, want := lipgloss.Height(rendered.String()), delegate.Height(); got != want {
		t.Fatalf("expected delegate output to honor its declared height: got %d, want %d:\n%s", got, want, plain)
	}
	if delegate.Height() != 3 {
		t.Fatalf("expected two title lines plus metadata, got delegate height %d", delegate.Height())
	}
	for _, wanted := range []string{"README green CLI", "codex · 02 Aug · 6 turns"} {
		if !strings.Contains(plain, wanted) {
			t.Fatalf("expected readable list content %q:\n%s", wanted, plain)
		}
	}
	for _, raw := range []string{"[delegated task]", "readme_green_cli", "(prompt not recorded)"} {
		if strings.Contains(plain, raw) {
			t.Fatalf("expected list title to omit backend notation %q:\n%s", raw, plain)
		}
	}
}

func TestShortSelectedRowKeepsMetadataDirectlyUnderTitle(t *testing.T) {
	m := sizedModel(contextPayload{
		Project: "/work/convo-explorer",
		Conversations: []conversation{{
			UUID:         "one",
			Source:       "codex",
			Timestamp:    "2026-08-02T21:33:21Z",
			TurnCount:    6,
			FirstMessage: "README green CLI",
		}},
	}, 90, 30)

	var rendered strings.Builder
	delegate := conversationDelegate{colors: m.colors, focused: true}
	delegate.Render(&rendered, m.conversations, 0, m.conversations.SelectedItem())
	lines := strings.Split(ansiSequence.ReplaceAllString(rendered.String(), ""), "\n")
	if len(lines) != delegate.Height() {
		t.Fatalf("expected exactly %d reserved row lines, got %d:\n%s", delegate.Height(), len(lines), rendered.String())
	}
	if !strings.Contains(lines[0], "README green CLI") || !strings.Contains(lines[1], "codex · 02 Aug · 6 turns") {
		t.Fatalf("expected title then metadata without an empty line between them:\n%s", rendered.String())
	}
}

func TestPreviewUsesComposedConversationLanguage(t *testing.T) {
	m := initialModel(contextPayload{
		Project: "/work/convo-explorer",
		Conversations: []conversation{
			{
				UUID:             "019fc465-4e56-7e61-9f93-aac628fd0594",
				Source:           "codex",
				Model:            "gpt-5.6-sol",
				Effort:           "max",
				FirstMessage:     "Build the polished public README",
				LastAgentMessage: "Created the verified draft.",
			},
		},
	})
	m.preview.SetWidth(90)
	m.preview.SetHeight(30)
	m.refreshPreview()

	preview := ansiSequence.ReplaceAllString(m.preview.View(), "")
	for _, wanted := range []string{"019fc465", "codex", "gpt-5.6-sol · max", "LATEST REPLY"} {
		if !strings.Contains(preview, wanted) {
			t.Fatalf("expected plain conversation detail %q in preview:\n%s", wanted, preview)
		}
	}
	for _, noisy := range []string{"SESSION SIGNAL", "TRANSMISSION", "LATEST RESPONSE"} {
		if strings.Contains(preview, noisy) {
			t.Fatalf("expected preview without cyber-console label %q:\n%s", noisy, preview)
		}
	}
}

func TestReadingHeaderUsesOneEditorialMetadataRhythm(t *testing.T) {
	m := sizedModel(contextPayload{
		Project: "/work/convo-explorer",
		Conversations: []conversation{{
			UUID:             "019fc465-4e56-7e61-9f93-aac628fd0594",
			Source:           "codex",
			Timestamp:        "2026-08-02T21:33:21Z",
			TurnCount:        6,
			FirstMessage:     "Review the reader",
			LastAgentMessage: "Complete.",
		}},
	}, 106, 30)

	preview := ansiSequence.ReplaceAllString(m.preview.GetContent(), "")
	if !strings.Contains(preview, "codex · 02 Aug 2026 · 6 turns · 019fc465") {
		t.Fatalf("expected one readable metadata rhythm:\n%s", preview)
	}
	if strings.Contains(preview, "2026-08-02") {
		t.Fatalf("expected the reading header to avoid raw ISO-date presentation:\n%s", preview)
	}
}

func TestMediumLayoutUsesAnInsetReadingMeasureAndSectionLandmarks(t *testing.T) {
	m := sizedModel(contextPayload{
		Project: "/work/convo-explorer",
		Conversations: []conversation{{
			UUID:             "019fc465-4e56-7e61-9f93-aac628fd0594",
			Source:           "codex",
			Timestamp:        "2026-08-02T21:33:21Z",
			TurnCount:        6,
			Model:            "gpt-5.6-sol",
			Effort:           "max",
			FirstMessage:     "[delegated task] readme_green_cli (prompt not recorded)",
			LastAgentMessage: "Created the polished README draft.",
		}},
	}, 106, 30)

	layout := m.layout()
	if got, want := layout.rightContent, layout.rightOuter-4; got != want {
		t.Fatalf("expected a two-cell reading inset on both sides: got content %d in outer width %d, want %d", got, layout.rightOuter, want)
	}

	view := m.View().Content
	plain := ansiSequence.ReplaceAllString(view, "")
	for _, wanted := range []string{"Recent conversations", "Conversation detail", "README green CLI", "OPENING MESSAGE", "LATEST REPLY"} {
		if !strings.Contains(plain, wanted) {
			t.Fatalf("expected composed medium-screen landmark %q:\n%s", wanted, plain)
		}
	}
	if got := lipgloss.Width(view); got != 106 {
		t.Fatalf("expected exact 106-column canvas, got %d", got)
	}
	if got := lipgloss.Height(view); got != 30 {
		reader := lipgloss.NewStyle().
			Width(layout.rightOuter).
			Height(max(1, layout.bodyHeight-1)).
			PaddingLeft(2).
			PaddingRight(2).
			Render(m.preview.View())
		rightContent := m.paneHeading("Conversation detail", false, layout.rightOuter) + "\n" + reader
		t.Fatalf("expected exact 30-row canvas, got %d (list=%d list-view=%d preview=%d reader=%d right=%d body=%d)",
			got, lipgloss.Height(m.conversations.View()), lipgloss.Height(m.listView(layout.leftContent)),
			lipgloss.Height(m.preview.View()), lipgloss.Height(reader), lipgloss.Height(rightContent), layout.bodyHeight)
	}
}

func TestPreviewDoesNotRepeatShortOpeningWhenTitleCarriesIt(t *testing.T) {
	const request = "Keep the complete response"
	m := sizedModel(contextPayload{
		Project: "/work/convo-explorer",
		Conversations: []conversation{{
			UUID:             "one",
			Source:           "codex",
			FirstMessage:     request,
			LastAgentMessage: "Complete reply",
		}},
	}, 100, 24)

	preview := ansiSequence.ReplaceAllString(m.preview.GetContent(), "")
	if strings.Count(preview, request) != 1 {
		t.Fatalf("expected a short opening to appear once as the reading title:\n%s", preview)
	}
	if strings.Contains(preview, "OPENING MESSAGE") {
		t.Fatalf("expected no redundant opening section when the title preserves it:\n%s", preview)
	}
}

func TestPreviewSoftWrapsWithoutDroppingReply(t *testing.T) {
	reply := "The complete reply remains available even when it is much wider than the preview pane."
	m := initialModel(contextPayload{
		Project: "/work/convo-explorer",
		Conversations: []conversation{
			{
				UUID:             "019fc465-4e56-7e61-9f93-aac628fd0594",
				Source:           "codex",
				FirstMessage:     "Keep the whole reply",
				LastAgentMessage: reply,
			},
		},
	})
	m.preview.SetWidth(24)
	m.preview.SetHeight(20)
	m.refreshPreview()

	if !m.preview.SoftWrap {
		t.Fatal("expected the preview viewport to soft-wrap long replies")
	}
	preview := whitespace.ReplaceAllString(ansiSequence.ReplaceAllString(m.preview.GetContent(), ""), " ")
	if !strings.Contains(preview, reply) {
		t.Fatalf("expected complete reply in viewport content:\n%s", m.preview.GetContent())
	}
}

func TestPreviewRendersConversationMessagesAsMarkdown(t *testing.T) {
	m := sizedModel(contextPayload{
		Project: "/work/convo-explorer",
		Conversations: []conversation{{
			UUID:             "one",
			Source:           "codex",
			FirstMessage:     "# Release notes\n\nShip the **reader**.",
			LastUserMessage:  "Please keep the [docs link](https://example.com/docs).",
			LastAgentMessage: "## Complete\n\n- Preserved *every* line\n\n```go\nfmt.Println(\"tail\")\n```",
		}},
	}, 110, 32)

	preview := ansiSequence.ReplaceAllString(m.preview.GetContent(), "")
	for _, wanted := range []string{"Release notes", "reader", "docs link", "Complete", "Preserved", "fmt.Println", "tail"} {
		if !strings.Contains(preview, wanted) {
			t.Fatalf("expected rendered Markdown content %q:\n%s", wanted, preview)
		}
	}
	for _, literal := range []string{"# Release notes", "**reader**", "](", "## Complete", "```go", "*every*"} {
		if strings.Contains(preview, literal) {
			t.Fatalf("expected Markdown syntax %q to be rendered, not shown literally:\n%s", literal, preview)
		}
	}
	if !strings.Contains(m.preview.GetContent(), "\x1b[") {
		t.Fatalf("expected Glamour styling in rendered message bodies:\n%s", m.preview.GetContent())
	}
}

func TestPreviewOmitsLatestUserSectionWhenBackendOmitsMessage(t *testing.T) {
	m := sizedModel(contextPayload{
		Project: "/work/convo-explorer",
		Conversations: []conversation{{
			UUID:             "one",
			Source:           "codex",
			FirstMessage:     "Only request",
			LastUserMessage:  "",
			LastAgentMessage: "Only reply",
		}},
	}, 100, 24)

	preview := ansiSequence.ReplaceAllString(m.preview.GetContent(), "")
	if strings.Contains(preview, "LATEST USER MESSAGE") {
		t.Fatalf("expected omitted backend field not to create a duplicate latest-user section:\n%s", preview)
	}
	if strings.Count(preview, "Only request") != 1 {
		t.Fatalf("expected the short opening to remain available once in the reading header:\n%s", preview)
	}
}

func TestTabSwitchesToDetailSpecificHelp(t *testing.T) {
	m := sizedModel(contextPayload{
		Project: "/work/convo-explorer",
		Conversations: []conversation{{
			UUID:             "one",
			Source:           "codex",
			FirstMessage:     "Review the reader",
			LastAgentMessage: "A reply",
		}},
	}, 110, 30)

	browseHelp := ansiSequence.ReplaceAllString(m.footer(), "")
	if !strings.Contains(browseHelp, "↑/↓ j/k move") || !strings.Contains(browseHelp, "/ filter") {
		t.Fatalf("expected browse-specific key hints:\n%s", browseHelp)
	}

	m = press(m, tea.KeyTab, "")
	detailHelp := ansiSequence.ReplaceAllString(m.footer(), "")
	if !strings.Contains(detailHelp, "↑/↓ j/k scroll") || !strings.Contains(detailHelp, "pgup/dn page") {
		t.Fatalf("expected detail-specific key hints after Tab:\n%s", detailHelp)
	}
	if strings.Contains(detailHelp, "j/k move") {
		t.Fatalf("expected browse movement hint to leave with list focus:\n%s", detailHelp)
	}
}

func TestDetailFocusUsesJToScrollWithoutMovingTheList(t *testing.T) {
	m := sizedModel(contextPayload{
		Project: "/work/convo-explorer",
		Conversations: []conversation{
			{
				UUID:             "one",
				Source:           "codex",
				FirstMessage:     "Long reply",
				LastAgentMessage: strings.Repeat("reader line\n", 80),
			},
			{
				UUID:             "two",
				Source:           "claude",
				FirstMessage:     "Second conversation",
				LastAgentMessage: "Do not select me.",
			},
		},
	}, 100, 18)

	m = press(m, tea.KeyTab, "")
	m = press(m, 'j', "j")

	if m.conversations.Index() != 0 {
		t.Fatalf("expected detail scrolling to keep list selection, got %d", m.conversations.Index())
	}
	if m.preview.YOffset() == 0 {
		t.Fatal("expected j to scroll the focused detail viewport")
	}
}

func TestDetailFocusCanReachTheActualReplyTail(t *testing.T) {
	const tail = "ACTUAL-REPLY-TAIL"
	m := sizedModel(contextPayload{
		Project: "/work/convo-explorer",
		Conversations: []conversation{{
			UUID:             "one",
			Source:           "codex",
			FirstMessage:     "Keep everything",
			LastAgentMessage: strings.Repeat("complete line\n", 100) + tail,
		}},
	}, 96, 16)

	m = press(m, tea.KeyTab, "")
	m = press(m, tea.KeyEnd, "")

	if !m.preview.AtBottom() {
		t.Fatalf("expected End to reach the viewport bottom, offset=%d", m.preview.YOffset())
	}
	if !strings.Contains(ansiSequence.ReplaceAllString(m.preview.View(), ""), tail) {
		t.Fatalf("expected visible tail after End:\n%s", m.preview.View())
	}
}

func TestSlashFilterIsVisibleAndEscapeClearsIt(t *testing.T) {
	m := sizedModel(contextPayload{
		Project: "/work/convo-explorer",
		Conversations: []conversation{
			{UUID: "one", Source: "codex", FirstMessage: "Ordinary session"},
			{UUID: "two", Source: "claude", FirstMessage: "Needle session"},
		},
	}, 110, 30)

	m = press(m, '/', "/")
	if !m.conversations.SettingFilter() {
		t.Fatal("expected slash to focus the Bubbles filter input")
	}
	m.conversations.SetFilterText("needle")
	m.refreshPreview()

	filtered := ansiSequence.ReplaceAllString(m.View().Content, "")
	if len(m.conversations.VisibleItems()) != 1 {
		t.Fatalf("expected one filtered item, got %d", len(m.conversations.VisibleItems()))
	}
	for _, wanted := range []string{"needle", "1 result", "Needle session"} {
		if !strings.Contains(strings.ToLower(filtered), strings.ToLower(wanted)) {
			t.Fatalf("expected visible filter state %q:\n%s", wanted, filtered)
		}
	}

	m = press(m, tea.KeyEscape, "")
	if m.conversations.FilterValue() != "" || len(m.conversations.VisibleItems()) != 2 {
		t.Fatalf("expected Escape to clear and exit filter, value=%q visible=%d",
			m.conversations.FilterValue(), len(m.conversations.VisibleItems()))
	}
}

func TestSelectedConversationRowsFillTheListWidth(t *testing.T) {
	const title = "Polished README"
	m := sizedModel(contextPayload{
		Project: "/work/convo-explorer",
		Conversations: []conversation{{
			UUID:         "one",
			Source:       "codex",
			Timestamp:    "2026-08-02T21:33:21Z",
			TurnCount:    5,
			FirstMessage: title,
		}},
	}, 110, 30)

	var selectedLine string
	for _, line := range strings.Split(m.conversations.View(), "\n") {
		if strings.Contains(line, title) {
			selectedLine = line
			break
		}
	}
	if selectedLine == "" {
		t.Fatalf("expected selected title in list:\n%s", m.conversations.View())
	}
	if lipgloss.Width(selectedLine) < m.conversations.Width()-1 {
		t.Fatalf("expected full-width selected row: got %d, want at least %d",
			lipgloss.Width(selectedLine), m.conversations.Width()-1)
	}
	fillAfterTitle := regexp.MustCompile(regexp.QuoteMeta(title) + `\x1b\[(?:0)?m\x1b\[[0-9;:]*48[0-9;:]*m {6,}\x1b\[(?:0)?m`)
	if !fillAfterTitle.MatchString(selectedLine) {
		t.Fatalf("expected selected background treatment to include trailing row fill:\n%q", selectedLine)
	}
}

func TestCompactLayoutKeepsBothPanesAndScrollStatusOnCanvas(t *testing.T) {
	m := sizedModel(contextPayload{
		Project: "/work/convo-explorer",
		Conversations: []conversation{
			{UUID: "one", Source: "codex", FirstMessage: "First conversation", LastAgentMessage: strings.Repeat("reply\n", 30)},
			{UUID: "two", Source: "claude", FirstMessage: "Second conversation"},
		},
	}, 90, 30)

	view := m.View().Content
	plain := ansiSequence.ReplaceAllString(view, "")
	for _, wanted := range []string{"Recent", "Conversation", "TOP", "1 / 2"} {
		if !strings.Contains(plain, wanted) {
			t.Fatalf("expected compact layout status %q:\n%s", wanted, plain)
		}
	}
	if got := lipgloss.Width(view); got != 90 {
		t.Fatalf("expected 90-column canvas, got %d", got)
	}
	if got := lipgloss.Height(view); got != 30 {
		t.Fatalf("expected 30-row canvas, got %d", got)
	}
	lines := strings.Split(ansiSequence.ReplaceAllString(view, ""), "\n")
	lastVisibleLine := lines[min(29, len(lines)-1)]
	if !strings.Contains(lastVisibleLine, "BROWSE") || !strings.Contains(lastVisibleLine, "TOP") {
		t.Fatalf("expected focus help and scroll state on the last visible row, got:\n%s", lastVisibleLine)
	}
}

func TestListDelegateNeverRendersMoreLinesThanItDeclares(t *testing.T) {
	m := sizedModel(contextPayload{
		Project: "/work/convo-explorer",
		Conversations: []conversation{{
			UUID:         "one",
			Source:       "codex",
			Timestamp:    "2026-08-03T20:00:00Z",
			TurnCount:    10,
			FirstMessage: "For THIS task you are the sole implementation worker, not an orchestrator.",
		}},
	}, 90, 30)

	item := m.conversations.SelectedItem()
	var rendered strings.Builder
	delegate := conversationDelegate{colors: m.colors, focused: true}
	delegate.Render(&rendered, m.conversations, 0, item)
	if got, want := lipgloss.Height(rendered.String()), delegate.Height(); got != want {
		t.Fatalf("expected delegate output to honor its three-line height, got %d:\n%s", got, rendered.String())
	}
	viewLines := strings.Split(ansiSequence.ReplaceAllString(m.View().Content, ""), "\n")
	for i, line := range viewLines {
		if !strings.Contains(line, "▌ For THIS task") {
			continue
		}
		if i+2 >= len(viewLines) || !strings.Contains(viewLines[i+1], "▌ implementation worker") ||
			!strings.Contains(viewLines[i+2], "▌ codex · 03 Aug · 10 turns") {
			t.Fatalf("expected composed pane to wrap the selected title above stable metadata:\n%s", strings.Join(viewLines, "\n"))
		}
		return
	}
	t.Fatal("expected selected conversation in composed pane")
}

func TestShiftTabMovesFocusWithoutLosingSelection(t *testing.T) {
	m := sizedModel(contextPayload{
		Project: "/work/convo-explorer",
		Conversations: []conversation{
			{UUID: "one", Source: "codex", FirstMessage: "First"},
			{UUID: "two", Source: "claude", FirstMessage: "Second"},
		},
	}, 110, 30)
	m.conversations.Select(1)
	m.refreshPreview()

	m, _ = pressKey(m, tea.KeyPressMsg{Code: tea.KeyTab, Mod: tea.ModShift})
	if m.focus != detailFocus {
		t.Fatalf("expected Shift+Tab to move focus to detail, got %v", m.focus)
	}
	if m.conversations.Index() != 1 {
		t.Fatalf("expected focus change to preserve selected row, got %d", m.conversations.Index())
	}

	m, _ = pressKey(m, tea.KeyPressMsg{Code: tea.KeyTab, Mod: tea.ModShift})
	if m.focus != browseFocus {
		t.Fatalf("expected second Shift+Tab to return to browse, got %v", m.focus)
	}
}

func TestCtrlCIsGlobalExitWithoutStealingOrdinaryQ(t *testing.T) {
	m := sizedModel(contextPayload{
		Project:       "/work/convo-explorer",
		Conversations: []conversation{{UUID: "one", Source: "codex", FirstMessage: "First"}},
	}, 110, 30)

	var cmd tea.Cmd
	m, cmd = pressKey(m, tea.KeyPressMsg{Code: 'q', Text: "q"})
	if cmd != nil {
		t.Fatal("expected ordinary q not to quit while browsing")
	}

	m = press(m, '/', "/")
	m, cmd = pressKey(m, tea.KeyPressMsg{Code: 'c', Mod: tea.ModCtrl})
	if cmd == nil {
		t.Fatal("expected Ctrl+C to remain an exit fallback while filtering")
	}
}

func TestClearingFilterRestoresThePreviousConversation(t *testing.T) {
	m := sizedModel(contextPayload{
		Project: "/work/convo-explorer",
		Conversations: []conversation{
			{UUID: "one", Source: "codex", FirstMessage: "First"},
			{UUID: "two", Source: "claude", FirstMessage: "Keep selected"},
			{UUID: "three", Source: "codex", FirstMessage: "Needle result"},
		},
	}, 110, 30)
	m.conversations.Select(1)
	m.refreshPreview()

	m = press(m, '/', "/")
	m.conversations.SetFilterText("needle")
	m.refreshPreview()
	if got := m.selectedID(); !strings.Contains(got, "three") {
		t.Fatalf("expected filtered result to become selected, got %q", got)
	}

	m = press(m, tea.KeyEscape, "")
	if got := m.selectedID(); !strings.Contains(got, "two") {
		t.Fatalf("expected Escape to restore the pre-filter selection, got %q", got)
	}
	if !strings.Contains(ansiSequence.ReplaceAllString(m.preview.GetContent(), ""), "Keep selected") {
		t.Fatalf("expected restored detail content:\n%s", m.preview.GetContent())
	}
}

func TestPreviewOmitsDuplicateLatestUserMessage(t *testing.T) {
	const request = "Keep the complete response"
	m := sizedModel(contextPayload{
		Project: "/work/convo-explorer",
		Conversations: []conversation{{
			UUID:             "one",
			Source:           "codex",
			FirstMessage:     request,
			LastUserMessage:  request,
			LastAgentMessage: "Complete reply",
		}},
	}, 100, 24)

	preview := ansiSequence.ReplaceAllString(m.preview.GetContent(), "")
	if strings.Contains(preview, "LATEST USER MESSAGE") {
		t.Fatalf("expected duplicate latest-user section to be omitted:\n%s", preview)
	}
	if strings.Count(preview, request) != 1 {
		t.Fatalf("expected the short opening once in the reading header, got:\n%s", preview)
	}
}

func TestFilterModeExposesAViewCursor(t *testing.T) {
	m := sizedModel(contextPayload{
		Project:       "/work/convo-explorer",
		Conversations: []conversation{{UUID: "one", Source: "codex", FirstMessage: "First"}},
	}, 110, 30)
	if m.View().Cursor != nil {
		t.Fatal("expected no terminal cursor while browsing")
	}

	m = press(m, '/', "/")
	view := m.View()
	if view.Cursor == nil {
		t.Fatal("expected the focused Bubbles filter input to expose its cursor")
	}
	if view.Cursor.Y < 1 || view.Cursor.Y >= m.height-1 {
		t.Fatalf("expected filter cursor on the application canvas, got y=%d", view.Cursor.Y)
	}
}

func TestTooSmallLayoutIsIntentionalAndExact(t *testing.T) {
	m := sizedModel(contextPayload{
		Project:       "/work/convo-explorer",
		Conversations: []conversation{{UUID: "one", Source: "codex", FirstMessage: "First"}},
	}, 60, 12)

	view := m.View().Content
	plain := ansiSequence.ReplaceAllString(view, "")
	for _, wanted := range []string{"AgentConvos", "needs at least 72x18", "60x12"} {
		if !strings.Contains(plain, wanted) {
			t.Fatalf("expected intentional too-small copy %q:\n%s", wanted, plain)
		}
	}
	if got := lipgloss.Width(view); got != 60 {
		t.Fatalf("expected 60-column too-small canvas, got %d", got)
	}
	if got := lipgloss.Height(view); got != 12 {
		t.Fatalf("expected 12-row too-small canvas, got %d", got)
	}
}

func TestEditorialLayoutUsesSurfacesInsteadOfBoxedPanes(t *testing.T) {
	m := sizedModel(contextPayload{
		Project:       "/work/convo-explorer",
		Conversations: []conversation{{UUID: "one", Source: "codex", FirstMessage: "First"}},
	}, 136, 65)

	plain := ansiSequence.ReplaceAllString(m.View().Content, "")
	for _, border := range []string{"╭", "╮", "╰", "╯"} {
		if strings.Contains(plain, border) {
			t.Fatalf("expected editorial surfaces rather than rounded pane boxes %q:\n%s", border, plain)
		}
	}
	if !strings.Contains(plain, "Recent") || !strings.Contains(plain, "Conversation") {
		t.Fatalf("expected both workspace regions:\n%s", plain)
	}
	if got := lipgloss.Width(m.View().Content); got != 136 {
		t.Fatalf("expected 136-column canvas, got %d", got)
	}
	if got := lipgloss.Height(m.View().Content); got != 65 {
		t.Fatalf("expected 65-row canvas, got %d", got)
	}
}

func TestResizePreservesSelectionFocusQueryAndReadingPosition(t *testing.T) {
	m := sizedModel(contextPayload{
		Project: "/work/convo-explorer",
		Conversations: []conversation{
			{UUID: "one", Source: "codex", FirstMessage: "First"},
			{
				UUID:             "two",
				Source:           "claude",
				FirstMessage:     "Keep selected",
				LastAgentMessage: strings.Repeat("complete line\n", 120) + "TAIL",
			},
		},
	}, 90, 30)
	m.conversations.Select(1)
	m.refreshPreview()
	m.focus = detailFocus
	m.preview.GotoBottom()
	m.conversations.SetFilterText("keep")
	m.conversations.SetFilterState(list.FilterApplied)

	updated, _ := m.Update(tea.WindowSizeMsg{Width: 136, Height: 65})
	m = updated.(model)
	if m.focus != detailFocus {
		t.Fatalf("expected resize to preserve detail focus, got %v", m.focus)
	}
	if got := m.selectedID(); !strings.Contains(got, "two") {
		t.Fatalf("expected resize to preserve selection, got %q", got)
	}
	if got := m.conversations.FilterValue(); got != "keep" {
		t.Fatalf("expected resize to preserve query, got %q", got)
	}
	if !m.preview.AtBottom() {
		t.Fatalf("expected resize to preserve bottom reading position, offset=%d", m.preview.YOffset())
	}
}

func TestAppliedFilterStillAllowsListNavigation(t *testing.T) {
	m := sizedModel(contextPayload{
		Project: "/work/convo-explorer",
		Conversations: []conversation{
			{UUID: "one", Source: "codex", FirstMessage: "Session one"},
			{UUID: "two", Source: "claude", FirstMessage: "Session two"},
			{UUID: "three", Source: "codex", FirstMessage: "Session three"},
		},
	}, 110, 30)
	m = press(m, '/', "/")
	m.conversations.SetFilterText("session")
	m.refreshPreview()

	m = press(m, 'j', "j")
	if got := m.selectedID(); !strings.Contains(got, "two") {
		t.Fatalf("expected j to move within applied results instead of restoring the anchor, got %q", got)
	}
	if !strings.Contains(ansiSequence.ReplaceAllString(m.preview.GetContent(), ""), "Session two") {
		t.Fatalf("expected filtered navigation to refresh detail:\n%s", m.preview.GetContent())
	}
}

func TestScrollStateSaysAllWhenTheWholeDetailFits(t *testing.T) {
	m := sizedModel(contextPayload{
		Project: "/work/convo-explorer",
		Conversations: []conversation{{
			UUID:             "one",
			Source:           "codex",
			FirstMessage:     "Short request",
			LastAgentMessage: "Short reply",
		}},
	}, 136, 65)

	if !m.preview.AtTop() || !m.preview.AtBottom() {
		t.Fatal("test requires the complete detail to fit in the viewport")
	}
	if got := m.scrollState(); got != "ALL" {
		t.Fatalf("expected fully visible scroll state ALL, got %q", got)
	}
}

func TestNoMatchStateNamesTheQueryAndRecovery(t *testing.T) {
	m := sizedModel(contextPayload{
		Project: "/work/convo-explorer",
		Conversations: []conversation{
			{UUID: "one", Source: "codex", FirstMessage: "First"},
			{UUID: "two", Source: "claude", FirstMessage: "Second"},
		},
	}, 90, 30)
	m.conversations.SetFilterText("absent")
	m.refreshPreview()

	plain := ansiSequence.ReplaceAllString(m.View().Content, "")
	for _, wanted := range []string{`No conversations match "absent".`, "Esc clears the filter.", "0 results of 2"} {
		if !strings.Contains(plain, wanted) {
			t.Fatalf("expected actionable no-match state %q:\n%s", wanted, plain)
		}
	}
}

func TestMissingMetadataIsOmittedCleanly(t *testing.T) {
	m := sizedModel(contextPayload{
		Project: "/work/convo-explorer",
		Conversations: []conversation{{
			UUID:             "one",
			Source:           "codex",
			FirstMessage:     "Recorded request",
			LastAgentMessage: "Recorded reply",
		}},
	}, 90, 30)

	plain := ansiSequence.ReplaceAllString(m.View().Content, "")
	if !strings.Contains(plain, "codex") {
		t.Fatalf("expected available source metadata:\n%s", plain)
	}
	for _, missing := range []string{"0 turns", "? · codex"} {
		if strings.Contains(plain, missing) {
			t.Fatalf("expected missing metadata %q to be omitted:\n%s", missing, plain)
		}
	}
}
