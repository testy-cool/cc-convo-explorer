package main

import (
	"regexp"
	"strings"
	"testing"

	tea "charm.land/bubbletea/v2"
	"charm.land/lipgloss/v2"
)

var ansiSequence = regexp.MustCompile(`\x1b\[[0-9;:]*m`)

func press(m model, code rune, text string) model {
	updated, _ := m.Update(tea.KeyPressMsg{Code: code, Text: text})
	return updated.(model)
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
	for _, wanted := range []string{"Recent", "Build the polished public README", "02 Aug", "codex · 5 turns"} {
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

func TestPreviewUsesPlainConversationLanguage(t *testing.T) {
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
	for _, wanted := range []string{"019fc465", "codex", "gpt-5.6-sol · max", "First message", "Agent's latest reply"} {
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
	if strings.Contains(preview, "Your latest message") {
		t.Fatalf("expected omitted backend field not to create a duplicate latest-user section:\n%s", preview)
	}
	if strings.Count(preview, "Only request") != 2 {
		t.Fatalf("expected one title and one first-message body, not a duplicated latest user message:\n%s", preview)
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
	if !strings.Contains(browseHelp, "j/k move") || !strings.Contains(browseHelp, "/ filter") {
		t.Fatalf("expected browse-specific key hints:\n%s", browseHelp)
	}

	m = press(m, tea.KeyTab, "")
	detailHelp := ansiSequence.ReplaceAllString(m.footer(), "")
	if !strings.Contains(detailHelp, "j/k scroll") || !strings.Contains(detailHelp, "pgup/dn page") {
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
}
