package inlinepicker

import (
	"errors"
	"strings"
	"testing"

	"charm.land/huh/v2"
	"github.com/charmbracelet/x/ansi"
)

func TestRecentPerSourceCapsEachSourceAndKeepsRecencyOrder(t *testing.T) {
	conversations := []Conversation{
		{UUID: "codex-old", Source: "codex", Timestamp: "2026-08-01T10:00:00Z"},
		{UUID: "claude-new", Source: "claude", Timestamp: "2026-08-09T10:00:00Z"},
		{UUID: "codex-new", Source: "codex", Timestamp: "2026-08-10T10:00:00Z"},
		{UUID: "codex-2", Source: "codex", Timestamp: "2026-08-08T10:00:00Z"},
		{UUID: "codex-3", Source: "codex", Timestamp: "2026-08-07T10:00:00Z"},
		{UUID: "codex-4", Source: "codex", Timestamp: "2026-08-06T10:00:00Z"},
		{UUID: "codex-5", Source: "codex", Timestamp: "2026-08-05T10:00:00Z"},
		{UUID: "codex-6", Source: "codex", Timestamp: "2026-08-04T10:00:00Z"},
	}

	got := RecentPerSource(conversations, 5)
	ids := make([]string, len(got))
	for index, conversation := range got {
		ids[index] = conversation.UUID
	}
	want := []string{"codex-new", "claude-new", "codex-2", "codex-3", "codex-4", "codex-5"}
	if strings.Join(ids, ",") != strings.Join(want, ",") {
		t.Fatalf("unexpected selection order: got %v want %v", ids, want)
	}
}

func TestOptionsExposePurposeSourceDateAndTurnsWithoutMetadataNoise(t *testing.T) {
	options := Options([]Conversation{{
		UUID:         "session-1",
		Source:       "codex",
		Timestamp:    "2026-08-03T18:41:54Z",
		TurnCount:    117,
		Model:        "gpt-test",
		Effort:       "xhigh",
		FirstMessage: "Fix the retry loop without changing the API contract.",
	}})

	if len(options) != 1 {
		t.Fatalf("got %d options, want 1", len(options))
	}
	if options[0].Title != "Fix the retry loop without changing the API contract." {
		t.Fatalf("unexpected title %q", options[0].Title)
	}
	for _, fragment := range []string{"codex", "03 Aug 2026", "117 turns"} {
		if !strings.Contains(options[0].Description, fragment) {
			t.Fatalf("description %q missing %q", options[0].Description, fragment)
		}
	}
	for _, noisy := range []string{"gpt-test", "xhigh"} {
		if strings.Contains(options[0].Description, noisy) {
			t.Fatalf("description %q contains noisy metadata %q", options[0].Description, noisy)
		}
	}
}

func TestDetailOmitsMissingAndDuplicateFieldsAndPreservesFullReply(t *testing.T) {
	reply := "## Done\n\n**The problem:** starts here.\n\n*Complete reply* and **verified result** with [proof](https://example.com) and `code`.\n\n" + strings.Repeat("complete reply ", 80) + "TAIL-SENTINEL"
	conversation := Conversation{
		UUID:             "session-1",
		Source:           "codex",
		Timestamp:        "2026-08-03T18:41:54Z",
		TurnCount:        8,
		Model:            "gpt-test",
		FirstMessage:     "Only request",
		LastUserMessage:  "Only request",
		LastAgentMessage: reply,
	}

	detail, err := RenderDetail(ContextPayload{Project: "/work/project"}, conversation, RenderOptions{Color: true, Width: 80})
	if err != nil {
		t.Fatal(err)
	}
	for _, fragment := range []string{"/work/project", "03 Aug 2026", "codex", "8 turns", "gpt-test", "First message", "Only request", "Agent reply", "TAIL-SENTINEL"} {
		if !strings.Contains(detail, fragment) {
			t.Fatalf("detail missing %q:\n%s", fragment, detail)
		}
	}
	if strings.Contains(detail, "Your latest message") {
		t.Fatalf("duplicate latest-user section was rendered:\n%s", detail)
	}
	plain := ansi.Strip(detail)
	literalMarkdownMarkers := []string{
		"## Done",
		"*Complete reply*",
		"**The problem:**",
		"**verified result**",
		"[proof](https://example.com)",
		"`code`",
	}
	for _, literalMarkdown := range literalMarkdownMarkers {
		if strings.Contains(plain, literalMarkdown) {
			t.Fatalf("literal Markdown %q was not rendered:\n%s", literalMarkdown, detail)
		}
	}
	plainDetail, err := RenderDetail(ContextPayload{Project: "/work/project"}, conversation, RenderOptions{Color: false, Width: 80})
	if err != nil {
		t.Fatal(err)
	}
	for _, literalMarkdown := range literalMarkdownMarkers {
		if strings.Contains(plainDetail, literalMarkdown) {
			t.Fatalf("literal Markdown %q remained in plain rendering:\n%s", literalMarkdown, plainDetail)
		}
	}
	for _, missing := range []string{"Summary", "Effort"} {
		if strings.Contains(detail, missing) {
			t.Fatalf("missing field %q should be omitted:\n%s", missing, detail)
		}
	}
}

func TestDetailIncludesDistinctLatestUserAndRealSummary(t *testing.T) {
	conversation := Conversation{
		Source:           "claude",
		Summary:          "Verified cache behavior.",
		FirstMessage:     "Investigate cache behavior.",
		LastUserMessage:  "What did the live check show?",
		LastAgentMessage: "It passed.",
	}

	detail, err := RenderDetail(ContextPayload{Project: "/work/project"}, conversation, RenderOptions{Width: 72})
	if err != nil {
		t.Fatal(err)
	}
	for _, fragment := range []string{"Summary", "Verified cache behavior.", "Your latest message", "What did the live check show?"} {
		if !strings.Contains(detail, fragment) {
			t.Fatalf("detail missing %q:\n%s", fragment, detail)
		}
	}
}

func TestRunTreatsUserCancellationAsSuccessWithoutPrintingDetail(t *testing.T) {
	var output strings.Builder
	code := Run(
		ContextPayload{Project: "/work", Conversations: []Conversation{{UUID: "one"}}},
		&output,
		func([]Option) (string, error) { return "", huh.ErrUserAborted },
		RenderOptions{Width: 80},
	)
	if code != 0 {
		t.Fatalf("cancel exit code = %d, want 0", code)
	}
	if output.Len() != 0 {
		t.Fatalf("cancel printed output %q", output.String())
	}
}

func TestRunPrintsSelectionAfterPickerLifecycleAndNoAltScreenSequence(t *testing.T) {
	var output strings.Builder
	payload := ContextPayload{Project: "/work", Conversations: []Conversation{{
		UUID:             "one",
		Source:           "codex",
		FirstMessage:     "Pick me",
		LastAgentMessage: "Complete answer",
	}}}

	code := Run(payload, &output, func([]Option) (string, error) { return "one", nil }, RenderOptions{Width: 80})
	if code != 0 {
		t.Fatalf("selection exit code = %d, want 0", code)
	}
	if !strings.Contains(output.String(), "Complete answer") {
		t.Fatalf("selected detail missing: %q", output.String())
	}
	if strings.Contains(output.String(), "\x1b[?1049h") {
		t.Fatalf("output entered alternate screen: %q", output.String())
	}
}

func TestRunReportsUnexpectedPickerFailure(t *testing.T) {
	var output strings.Builder
	code := Run(
		ContextPayload{Conversations: []Conversation{{UUID: "one"}}},
		&output,
		func([]Option) (string, error) { return "", errors.New("terminal failed") },
		RenderOptions{Width: 80},
	)
	if code == 0 {
		t.Fatal("unexpected picker failure returned success")
	}
}
