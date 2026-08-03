package main

import (
	"regexp"
	"strings"
	"testing"
)

var ansiSequence = regexp.MustCompile(`\x1b\[[0-9;:]*m`)

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
	if !strings.Contains(ansiSequence.ReplaceAllString(m.preview.GetContent(), ""), reply) {
		t.Fatalf("expected complete reply in viewport content:\n%s", m.preview.GetContent())
	}
}
