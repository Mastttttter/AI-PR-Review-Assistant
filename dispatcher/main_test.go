package main

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/router-for-me/CLIProxyAPI/v7/sdk/config"

	"github.com/apr-review/dispatcher/tempkey"
)

func setupTestRouter(t *testing.T) (*gin.Engine, *tempkey.Provider) {
	t.Helper()
	gin.SetMode(gin.TestMode)

	prov := tempkey.NewProvider(10 * time.Minute)

	r := gin.New()
	r.GET("/health", func(c *gin.Context) {
		c.JSON(http.StatusOK, gin.H{"status": "ok"})
	})
	r.POST("/api/issue-key", func(c *gin.Context) {
		key := generateKey()
		prov.IssueKey(key)
		c.JSON(http.StatusOK, gin.H{
			"api_key":         key,
			"base_uri":        "http://127.0.0.1:18318",
			"model":           "gpt-4o-mini",
			"openai_model":    "gpt-4o-mini",
			"anthropic_model": "claude-sonnet-4-6",
			"expires_in":      600,
		})
	})

	return r, prov
}

func TestHealthEndpoint(t *testing.T) {
	r, _ := setupTestRouter(t)

	req := httptest.NewRequest("GET", "/health", nil)
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Fatalf("expected status 200, got %d", w.Code)
	}

	var body map[string]string
	json.Unmarshal(w.Body.Bytes(), &body)
	if body["status"] != "ok" {
		t.Fatalf("expected status 'ok', got '%s'", body["status"])
	}
}

func TestIssueKeyReturnsValidResponse(t *testing.T) {
	r, _ := setupTestRouter(t)

	req := httptest.NewRequest("POST", "/api/issue-key", nil)
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Fatalf("expected status 200, got %d", w.Code)
	}

	var body map[string]interface{}
	json.Unmarshal(w.Body.Bytes(), &body)

	apiKey, ok := body["api_key"].(string)
	if !ok || apiKey == "" {
		t.Fatal("expected non-empty api_key")
	}
	if !strings.HasPrefix(apiKey, "tmp-") {
		t.Fatalf("api_key should start with 'tmp-', got '%s'", apiKey)
	}
	hexPart := strings.TrimPrefix(apiKey, "tmp-")
	if len(hexPart) != 32 {
		t.Fatalf("expected 32 hex chars after prefix, got %d chars", len(hexPart))
	}

	if body["base_uri"] != "http://127.0.0.1:18318" {
		t.Fatalf("expected base_uri 'http://127.0.0.1:18318', got '%v'", body["base_uri"])
	}

	if body["model"] != "gpt-4o-mini" {
		t.Fatalf("expected model 'gpt-4o-mini', got '%v'", body["model"])
	}

	if body["openai_model"] != "gpt-4o-mini" {
		t.Fatalf("expected openai_model 'gpt-4o-mini', got '%v'", body["openai_model"])
	}

	if body["anthropic_model"] != "claude-sonnet-4-6" {
		t.Fatalf("expected anthropic_model 'claude-sonnet-4-6', got '%v'", body["anthropic_model"])
	}

	ei, ok := body["expires_in"].(float64)
	if !ok || int(ei) != 600 {
		t.Fatalf("expected expires_in 600, got %v", body["expires_in"])
	}
}

func TestKeyRotation(t *testing.T) {
	r, prov := setupTestRouter(t)

	req1 := httptest.NewRequest("POST", "/api/issue-key", nil)
	w1 := httptest.NewRecorder()
	r.ServeHTTP(w1, req1)

	var body1 map[string]interface{}
	json.Unmarshal(w1.Body.Bytes(), &body1)
	key1 := body1["api_key"].(string)

	req2 := httptest.NewRequest("POST", "/api/issue-key", nil)
	w2 := httptest.NewRecorder()
	r.ServeHTTP(w2, req2)

	var body2 map[string]interface{}
	json.Unmarshal(w2.Body.Bytes(), &body2)
	key2 := body2["api_key"].(string)

	if key1 == key2 {
		t.Fatal("expected different keys for sequential calls (rotation)")
	}

	// Verify the first key was destroyed by rotation
	if !prov.IsExpired(key1) {
		t.Fatal("first key should be expired after rotation")
	}
}

func TestConcurrentAccess(t *testing.T) {
	r, _ := setupTestRouter(t)

	var wg sync.WaitGroup
	keys := make([]string, 0, 50)
	var mu sync.Mutex

	for i := 0; i < 50; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			req := httptest.NewRequest("POST", "/api/issue-key", nil)
			w := httptest.NewRecorder()
			r.ServeHTTP(w, req)

			if w.Code != http.StatusOK {
				t.Errorf("concurrent request returned %d", w.Code)
			}

			var body map[string]interface{}
			json.Unmarshal(w.Body.Bytes(), &body)
			key := body["api_key"].(string)

			mu.Lock()
			keys = append(keys, key)
			mu.Unlock()
		}()
	}
	wg.Wait()

	if len(keys) != 50 {
		t.Fatalf("expected 50 keys, got %d", len(keys))
	}
}

func TestExpiredKeyRejection(t *testing.T) {
	shortProv := tempkey.NewProvider(1 * time.Millisecond)
	shortProv.IssueKey("tmp-short-lived")

	time.Sleep(10 * time.Millisecond)

	req := httptest.NewRequest("GET", "/", nil)
	req.Header.Set("Authorization", "Bearer tmp-short-lived")
	_, err := shortProv.Authenticate(context.Background(), req)
	if err == nil {
		t.Fatal("expected auth error for expired key")
	}
}

func TestMissingConfigError(t *testing.T) {
	_, err := config.LoadConfig("/nonexistent/path/config.yaml")
	if err == nil {
		t.Fatal("expected error loading non-existent config")
	}
}

func TestGenerateKeyUniqueness(t *testing.T) {
	seen := make(map[string]bool)
	for i := 0; i < 100; i++ {
		key := generateKey()
		if seen[key] {
			t.Fatal("generateKey produced duplicate key")
		}
		seen[key] = true
		if !strings.HasPrefix(key, "tmp-") {
			t.Fatalf("key should start with 'tmp-', got '%s'", key)
		}
	}
}

func TestEnvOpenAIModelDefaults(t *testing.T) {
	t.Setenv("DISPATCHER_LLM_MODEL", "custom-model")
	cfg := &config.Config{}
	result := envOpenAIModel(cfg)
	if result != "custom-model" {
		t.Fatalf("expected env model 'custom-model', got '%s'", result)
	}
}

func TestEnvOpenAIModelFallbackToConfig(t *testing.T) {
	cfg := &config.Config{}
	cfg.OpenAICompatibility = []config.OpenAICompatibility{
		{
			Models: []config.OpenAICompatibilityModel{
				{Name: "claude-opus"},
			},
		},
	}
	result := envOpenAIModel(cfg)
	if result != "claude-opus" {
		t.Fatalf("expected config model 'claude-opus', got '%s'", result)
	}
}

func TestEnvAnthropicModelDefaults(t *testing.T) {
	t.Setenv("DISPATCHER_ANTHROPIC_MODEL", "custom-claude")
	cfg := &config.Config{}
	result := envAnthropicModel(cfg)
	if result != "custom-claude" {
		t.Fatalf("expected env model 'custom-claude', got '%s'", result)
	}
}

func TestEnvAnthropicModelFallbackToConfig(t *testing.T) {
	cfgData := []byte(`
port: 8318
api-keys: ["test-key"]
claude-api-key:
  - api-key: "sk-test"
    models:
      - name: "claude-opus-4-7"
        alias: "claude-opus"
`)
	cfg, err := config.ParseConfigBytes(cfgData)
	if err != nil {
		t.Fatalf("failed to parse config: %v", err)
	}
	result := envAnthropicModel(cfg)
	if result != "claude-opus-4-7" {
		t.Fatalf("expected config model 'claude-opus-4-7', got '%s'", result)
	}
}

func TestEnvAnthropicModelReturnsEmptyWhenNoConfig(t *testing.T) {
	cfg := &config.Config{}
	result := envAnthropicModel(cfg)
	if result != "" {
		t.Fatalf("expected empty string for no config, got '%s'", result)
	}
}
