package main

import (
	"crypto/rand"
	"encoding/hex"
	"fmt"
	"log"
	"net/http"
	"os"
	"sync"
	"time"

	"github.com/gin-gonic/gin"
)

type apiKey struct {
	Key       string
	ExpiresAt time.Time
}

var (
	mu        sync.Mutex
	currentKey *apiKey
)

func main() {
	apiKeyEnv := os.Getenv("DISPATCHER_LLM_API_KEY")
	if apiKeyEnv == "" {
		log.Fatal("DISPATCHER_LLM_API_KEY environment variable is required but not set")
	}

	baseURL := os.Getenv("DISPATCHER_LLM_BASE_URL")
	if baseURL == "" {
		baseURL = "https://api.openai.com/v1"
	}

	model := os.Getenv("DISPATCHER_LLM_MODEL")
	if model == "" {
		model = "gpt-4o-mini"
	}

	port := os.Getenv("DISPATCHER_PORT")
	if port == "" {
		port = "8318"
	}

	r := gin.Default()

	r.GET("/health", func(c *gin.Context) {
		c.JSON(http.StatusOK, gin.H{"status": "ok"})
	})

	r.POST("/api/issue-key", func(c *gin.Context) {
		key, expiresIn := issueKey(10 * time.Minute)
		c.JSON(http.StatusOK, gin.H{
			"api_key":    key,
			"base_uri":   fmt.Sprintf("http://dispatcher:%s", port),
			"model":      model,
			"expires_in": int(expiresIn.Seconds()),
		})
	})

	log.Printf("Starting dispatcher server on port %s", port)
	if err := r.Run(":" + port); err != nil {
		log.Fatalf("Failed to start server: %v", err)
	}
}

func issueKey(ttl time.Duration) (string, time.Duration) {
	mu.Lock()
	defer mu.Unlock()

	now := time.Now()
	if currentKey != nil && now.Before(currentKey.ExpiresAt) {
		currentKey = nil
	}

	raw := make([]byte, 16)
	if _, err := rand.Read(raw); err != nil {
		panic(fmt.Sprintf("failed to generate random key: %v", err))
	}
	key := "tmp-" + hex.EncodeToString(raw)
	expiresAt := now.Add(ttl)
	currentKey = &apiKey{Key: key, ExpiresAt: expiresAt}

	return key, ttl
}
