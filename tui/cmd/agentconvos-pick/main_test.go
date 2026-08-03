package main

import (
	"bytes"
	"errors"
	"strings"
	"testing"

	"charm.land/huh/v2"

	"github.com/testy-cool/agentconvos/tui/inlinepicker"
)

func TestHuhSelectorCancelsOnEscapeWithoutAlternateScreen(t *testing.T) {
	input := bytes.NewBufferString("\x1b")
	var output bytes.Buffer
	selector := huhSelector("/work/project", 100, 30, input, &output)

	_, err := selector([]inlinepicker.Option{{
		Title:       "Fix the retry loop",
		Description: "codex · 03 Aug 2026 · 8 turns",
		Value:       "session-1",
	}})
	if !errors.Is(err, huh.ErrUserAborted) {
		t.Fatalf("escape error = %v, want ErrUserAborted", err)
	}
	if strings.Contains(output.String(), "\x1b[?1049h") {
		t.Fatalf("picker entered alternate screen: %q", output.String())
	}
}

func TestHuhSelectorMovesWithArrowAndAcceptsWithEnter(t *testing.T) {
	input := bytes.NewBufferString("\x1b[B\r")
	var output bytes.Buffer
	selector := huhSelector("/work/project", 100, 30, input, &output)

	selected, err := selector([]inlinepicker.Option{
		{Title: "First", Description: "codex · 03 Aug 2026 · 8 turns", Value: "first"},
		{Title: "Second", Description: "claude · 02 Aug 2026 · 4 turns", Value: "second"},
	})
	if err != nil {
		t.Fatal(err)
	}
	if selected != "second" {
		t.Fatalf("selected %q, want second", selected)
	}
	if strings.Contains(output.String(), "\x1b[?1049h") {
		t.Fatalf("picker entered alternate screen: %q", output.String())
	}
}

func TestOptionLabelKeepsMetadataVisibleAfterTruncatingLongPurpose(t *testing.T) {
	label := optionLabel(inlinepicker.Option{
		Title:       strings.Repeat("purpose ", 30),
		Description: "claude · 03 Aug 2026 · 12 turns",
	}, 90)

	if !strings.Contains(label, "claude · 03 Aug 2026 · 12 turns") {
		t.Fatalf("label lost metadata: %q", label)
	}
	if !strings.Contains(label, "…") {
		t.Fatalf("long purpose was not truncated: %q", label)
	}
}
