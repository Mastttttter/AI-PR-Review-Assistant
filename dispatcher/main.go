package main

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"errors"
	"fmt"
	"log"
	"net/http"
	"os"
	"strconv"
	"time"

	"github.com/gin-gonic/gin"
	sdkaccess "github.com/router-for-me/CLIProxyAPI/v7/sdk/access"
	sdkapi "github.com/router-for-me/CLIProxyAPI/v7/sdk/api"
	"github.com/router-for-me/CLIProxyAPI/v7/sdk/api/handlers"
	"github.com/router-for-me/CLIProxyAPI/v7/sdk/cliproxy"
	"github.com/router-for-me/CLIProxyAPI/v7/sdk/config"

	"github.com/apr-review/dispatcher/tempkey"
)

func main() {
	keyTTL := envInt("DISPATCHER_KEY_TTL", 600)
	prov := tempkey.NewProvider(keyTTL)

	cfg, err := config.LoadConfig("config.yaml")
	if err != nil {
		log.Fatalf("Failed to load config: %v", err)
	}

	if envPort := os.Getenv("DISPATCHER_PORT"); envPort != "" {
		if p, err := strconv.Atoi(envPort); err == nil {
			cfg.Port = p
		}
	}

	model := envOpenAIModel(cfg)
	anthropicModel := envAnthropicModel(cfg)

	accessMgr := sdkaccess.NewManager()
	sdkaccess.RegisterProvider(prov.Identifier(), prov)
	accessMgr.SetProviders(sdkaccess.RegisteredProviders())

	svc, err := cliproxy.NewBuilder().
		WithConfig(cfg).
		WithConfigPath("config.yaml").
		WithRequestAccessManager(accessMgr).
		WithServerOptions(
			sdkapi.WithRouterConfigurator(func(e *gin.Engine, _ *handlers.BaseAPIHandler, _ *config.Config) {
				e.GET("/health", func(c *gin.Context) {
					c.JSON(http.StatusOK, gin.H{"status": "ok"})
				})
				e.POST("/api/issue-key", func(c *gin.Context) {
					key := generateKey()
					prov.IssueKey(key)
					c.JSON(http.StatusOK, gin.H{
						"api_key":         key,
						"base_uri":        fmt.Sprintf("http://127.0.0.1:%d", cfg.Port),
						"model":           model,
						"openai_model":    model,
						"anthropic_model": anthropicModel,
						"expires_in":      int(keyTTL.Seconds()),
					})
				})
			}),
		).
		Build()
	if err != nil {
		log.Fatalf("Failed to build service: %v", err)
	}

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	log.Printf("Starting dispatcher server on port %d", cfg.Port)
	if err := svc.Run(ctx); err != nil && !errors.Is(err, context.Canceled) {
		log.Fatalf("Server error: %v", err)
	}
}

func envOpenAIModel(cfg *config.Config) string {
	if m := os.Getenv("DISPATCHER_LLM_MODEL"); m != "" {
		return m
	}
	if len(cfg.OpenAICompatibility) > 0 && len(cfg.OpenAICompatibility[0].Models) > 0 {
		return cfg.OpenAICompatibility[0].Models[0].Name
	}
	return "gpt-4o-mini"
}

func envAnthropicModel(cfg *config.Config) string {
	if m := os.Getenv("DISPATCHER_ANTHROPIC_MODEL"); m != "" {
		return m
	}
	if len(cfg.ClaudeKey) > 0 && len(cfg.ClaudeKey[0].Models) > 0 {
		return cfg.ClaudeKey[0].Models[0].Name
	}
	return ""
}

func envInt(key string, defaultVal int) time.Duration {
	if v := os.Getenv(key); v != "" {
		if n, err := strconv.Atoi(v); err == nil && n > 0 {
			return time.Duration(n) * time.Second
		}
	}
	return time.Duration(defaultVal) * time.Second
}

func generateKey() string {
	raw := make([]byte, 16)
	if _, err := rand.Read(raw); err != nil {
		panic(fmt.Sprintf("failed to generate random key: %v", err))
	}
	return "tmp-" + hex.EncodeToString(raw)
}
