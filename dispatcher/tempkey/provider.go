// Package tempkey provides a custom sdk/access Provider that manages
// temporary API keys with TTL-based expiry for the dispatcher service.
package tempkey

import (
	"context"
	"net/http"
	"strings"
	"sync"
	"time"

	sdkaccess "github.com/router-for-me/CLIProxyAPI/v7/sdk/access"
)

const providerType = "temp-key"

// KeyEntry holds a single temporary key with its expiry.
type KeyEntry struct {
	Key       string
	ExpiresAt time.Time
}

// Provider implements sdkaccess.Provider for temporary key management.
type Provider struct {
	mu   sync.RWMutex
	keys map[string]*KeyEntry
	ttl  time.Duration
}

// NewProvider creates a Provider with the given TTL for temp keys.
func NewProvider(ttl time.Duration) *Provider {
	return &Provider{
		keys: make(map[string]*KeyEntry),
		ttl:  ttl,
	}
}

// Identifier returns the provider type string.
func (p *Provider) Identifier() string {
	return providerType
}

// Authenticate checks the request for a Bearer token, X-Api-Key header,
// or ?key= query parameter and validates it against the temp key map.
func (p *Provider) Authenticate(ctx context.Context, r *http.Request) (*sdkaccess.Result, *sdkaccess.AuthError) {
	key := extractKey(r)
	if key == "" {
		return nil, sdkaccess.NewNotHandledError()
	}

	p.mu.RLock()
	entry, exists := p.keys[key]
	p.mu.RUnlock()

	if !exists {
		return nil, sdkaccess.NewInvalidCredentialError()
	}

	if time.Now().After(entry.ExpiresAt) {
		return nil, sdkaccess.NewNotHandledError()
	}

	return &sdkaccess.Result{
		Provider:  providerType,
		Principal: "temp-key-user",
	}, nil
}

// IssueKey generates a new temp key, destroying any existing valid key first.
func (p *Provider) IssueKey(rawKey string) {
	p.mu.Lock()
	defer p.mu.Unlock()

	now := time.Now()
	for k, e := range p.keys {
		if now.Before(e.ExpiresAt) {
			delete(p.keys, k)
		}
	}

	p.keys[rawKey] = &KeyEntry{
		Key:       rawKey,
		ExpiresAt: now.Add(p.ttl),
	}
}

// IsExpired checks whether a key exists and is not yet expired.
func (p *Provider) IsExpired(key string) bool {
	p.mu.RLock()
	defer p.mu.RUnlock()
	entry, exists := p.keys[key]
	if !exists {
		return true
	}
	return time.Now().After(entry.ExpiresAt)
}

func extractKey(r *http.Request) string {
	if auth := r.Header.Get("Authorization"); strings.HasPrefix(auth, "Bearer ") {
		return strings.TrimPrefix(auth, "Bearer ")
	}
	if key := r.Header.Get("X-Api-Key"); key != "" {
		return key
	}
	return r.URL.Query().Get("key")
}
