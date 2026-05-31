package tempkey

import (
	"context"
	"net/http/httptest"
	"testing"
	"time"
)

func TestAuthenticateWithBearerToken(t *testing.T) {
	prov := NewProvider(10 * time.Minute)
	prov.IssueKey("tmp-test-key-1234")

	req := httptest.NewRequest("GET", "/", nil)
	req.Header.Set("Authorization", "Bearer tmp-test-key-1234")

	result, err := prov.Authenticate(context.Background(), req)
	if err != nil {
		t.Fatalf("unexpected auth error: %v", err)
	}
	if result.Provider != "temp-key" {
		t.Fatalf("expected provider 'temp-key', got '%s'", result.Provider)
	}
}

func TestAuthenticateWithXApiKey(t *testing.T) {
	prov := NewProvider(10 * time.Minute)
	prov.IssueKey("tmp-x-api-key")

	req := httptest.NewRequest("GET", "/", nil)
	req.Header.Set("X-Api-Key", "tmp-x-api-key")

	result, err := prov.Authenticate(context.Background(), req)
	if err != nil {
		t.Fatalf("unexpected auth error: %v", err)
	}
	if result == nil {
		t.Fatal("expected non-nil result")
	}
}

func TestAuthenticateWithQueryParam(t *testing.T) {
	prov := NewProvider(10 * time.Minute)
	prov.IssueKey("tmp-query-key")

	req := httptest.NewRequest("GET", "/?key=tmp-query-key", nil)

	result, err := prov.Authenticate(context.Background(), req)
	if err != nil {
		t.Fatalf("unexpected auth error: %v", err)
	}
	if result == nil {
		t.Fatal("expected non-nil result")
	}
}

func TestAuthenticateInvalidKey(t *testing.T) {
	prov := NewProvider(10 * time.Minute)
	prov.IssueKey("tmp-valid-key")

	req := httptest.NewRequest("GET", "/", nil)
	req.Header.Set("Authorization", "Bearer tmp-wrong-key")

	_, err := prov.Authenticate(context.Background(), req)
	if err == nil {
		t.Fatal("expected auth error for invalid key")
	}
}

func TestAuthenticateExpiredKey(t *testing.T) {
	prov := NewProvider(1 * time.Millisecond)
	prov.IssueKey("tmp-expired-key")

	time.Sleep(10 * time.Millisecond)

	req := httptest.NewRequest("GET", "/", nil)
	req.Header.Set("Authorization", "Bearer tmp-expired-key")

	_, err := prov.Authenticate(context.Background(), req)
	if err == nil {
		t.Fatal("expected auth error for expired key")
	}
}

func TestAuthenticateNoCredentials(t *testing.T) {
	prov := NewProvider(10 * time.Minute)

	req := httptest.NewRequest("GET", "/", nil)

	_, err := prov.Authenticate(context.Background(), req)
	if err == nil {
		t.Fatal("expected auth error for no credentials")
	}
}

func TestIssueKeyRotation(t *testing.T) {
	prov := NewProvider(10 * time.Minute)
	prov.IssueKey("tmp-first-key")
	prov.IssueKey("tmp-second-key")

	if !prov.IsExpired("tmp-first-key") {
		t.Fatal("first key should be expired after rotation")
	}
	if prov.IsExpired("tmp-second-key") {
		t.Fatal("second key should be valid after rotation")
	}
}

func TestIsExpiredNonExistentKey(t *testing.T) {
	prov := NewProvider(10 * time.Minute)
	if !prov.IsExpired("nonexistent") {
		t.Fatal("non-existent key should be reported as expired")
	}
}

func TestConcurrentIssueKey(t *testing.T) {
	prov := NewProvider(10 * time.Minute)
	done := make(chan bool)

	for i := 0; i < 50; i++ {
		go func(n int) {
			key := "tmp-concurrent-" + string(rune('0'+n%10))
			prov.IssueKey(key)
			done <- true
		}(i)
	}

	for i := 0; i < 50; i++ {
		<-done
	}
}

func TestIdentifier(t *testing.T) {
	prov := NewProvider(10 * time.Minute)
	if prov.Identifier() != "temp-key" {
		t.Fatalf("expected identifier 'temp-key', got '%s'", prov.Identifier())
	}
}

func TestAuthenticateNotHandledForNonTempKeyFormat(t *testing.T) {
	prov := NewProvider(10 * time.Minute)
	prov.IssueKey("tmp-my-key")

	// A key without tmp- prefix should still be checked but will be invalid
	req := httptest.NewRequest("GET", "/", nil)
	req.Header.Set("Authorization", "Bearer static-admin-key")

	_, err := prov.Authenticate(context.Background(), req)
	if err == nil {
		t.Fatal("expected auth error for non-temp key")
	}
}

func TestNewProviderDefaultTTL(t *testing.T) {
	prov := NewProvider(600 * time.Second)
	if prov.ttl != 600*time.Second {
		t.Fatalf("expected ttl 600s, got %v", prov.ttl)
	}
	if prov.keys == nil {
		t.Fatal("expected non-nil keys map")
	}
}
