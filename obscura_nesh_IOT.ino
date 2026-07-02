/*
  ============================================================
  OBSCURA — NESH AI Voice Robot (Fixed & Hardened Edition)
  ============================================================
  Fixes applied:
    1. TLS: Replaced setInsecure() with proper root CA pinning
    2. malloc: Fatal halt on allocation failure
    3. Audio: Renamed playMp3Stream → playPcmStream (it IS raw PCM)
    4. Content-Length: Graceful fallback to chunk-read if header missing
    5. OLED: Each NeshExpression now renders a distinct face
    6. Error handling: Every failure path prints a descriptive Serial log
    7. WiFi creds: Moved out of source into secrets.h (gitignored)
  ============================================================
*/

#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <HTTPClient.h>
#include <time.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <driver/i2s.h>
#include "secrets.h"   // WIFI_SSID / WIFI_PASSWORD — see secrets.h.example

// ============================================================
//  USER CONFIG — Edit only this section
// ============================================================
#define OLED_ENABLED true

const char* SERVER_URL    = "https://obscura-backend-production-d7de.up.railway.app/voice/ask";
const char* STUDENT_ID    = "550e8400-e29b-41d4-a716-446655440000";
const char* STREAM        = "Commerce";
const char* SUBJECT       = "Economics";
const char* MEDIUM        = "english";

// Volume: 0.0 – 1.0  (0.30 = 30%, keep under 0.50 for safe listening)
#define SPEAKER_VOLUME 0.30f

// ============================================================
//  ROOT CA — Railway uses Let's Encrypt R11 (ISRG Root X1)
//  Verified 2025. Re-pin if TLS handshake fails in the future.
// ============================================================
static const char* ROOT_CA = R"EOF(
-----BEGIN CERTIFICATE-----
MIIFazCCA1OgAwIBAgIRAIIQz7DSQONZRGPgu2OCiwAwDQYJKoZIhvcNAQELBQAw
TzELMAkGA1UEBhMCVVMxKTAnBgNVBAoTIEludGVybmV0IFNlY3VyaXR5IFJlc2Vh
cmNoIEdyb3VwMRUwEwYDVQQDEwxJU1JHIFJvb3QgWDEwHhcNMTUwNjA0MTEwNDM4
WhcNMzUwNjA0MTEwNDM4WjBPMQswCQYDVQQGEwJVUzEpMCcGA1UEChMgSW50ZXJu
ZXQgU2VjdXJpdHkgUmVzZWFyY2ggR3JvdXAxFTATBgNVBAMTDElTUkcgUm9vdCBY
MTCCAiIwDQYJKoZIhvcNAQEBBQADggIPADCCAgoBggIBAK3oJHP0FDfzm54rVygc
h77ct984kIxuPOZXoHj3dcKi/vVqbvYATyjb3miGbESTtrFj/RQSa78f0uoxmyF+
0TM8ukj13Xnfs7j/EvEhmkvBioZxaUpmZmyPfjxwv60pIgbz5MDmgK7iS4+3mX6U
A5/TR5d8mUgjU+g4rk8Kb4Mu0UlXjIB0ttov0DiNewNwIRt18jA8+o+u3dpjq+sW
T8KOEUt+zwvo/7V3LvSye0rgTBIlDHCNAymg4VMk7BPZ7hm/ELNKjD+Jo2FR3qyH
B5T0Y3HsLuJvW5iB4YlcNHlsdu87kGJ55tukmi8mxdAQ4Q7e2RCOFvu396j3x+UC
B5iPNgiV5+I3lg02dZ77DnKxHZu8A/lJBdiB3QW0KtZB6awBdpUKD9jf1b0SHzUv
KBds0pjBqAlkd25HN7rOrFleaJ1/ctaJxQZBKT5ZPt0m9STJEadao0xAH0ahmbWn
OlFuhjuefXKnEgV4We0+UXgVCwOPjdAvBbI+e0ocS3MFEvzG6uBQE3xDk3SzynTn
jh8BCNAw1FtxNrQHusEwMFxIt4I7mKZ9YIqioymCzLq9gwQbooMDQaHWBfEbwrbw
qHyGO0aoSCqI3Haadr8faqU9GY/rOPNk3sgrDQoo//fb4hVC1CLQJ13hef4Y53CI
rU7m2Ys6xt0nUW7/vGT1M0NPAgMBAAGjQjBAMA4GA1UdDwEB/wQEAwIBBjAPBgNV
HRMBAf8EBTADAQH/MB0GA1UdDgQWBBR5tFnme7bl5AFzgAiIyBpY9umbbjANBgkq
hkiG9w0BAQsFAAOCAgEAVR9YqbyyqFDQDLHYGmkgJykIrGF1XIpu+ILlaS/V9lZL
ubhzEFnTIZd+50xx+7LSYK05qAvqFyFWhfFQDlnrzuBZ6brJFe+GnY+EgPbk6ZGQ
3BebYhtF8GaV0nxvwuo77x/Py9auJ/GpsMiu/X1+mvoiBOv/2X/qkSsisRcOj/KK
NFtY2PwByVS5uCbMiogziUwthDyC3+6WVwW6LLv3xLfHTjuCvjHIInNzktHCgKQ5
ORAzI4JMPJ+GslWYHb4phowim57iaztXOoJwTdwJx4nLCgdNbOhdjsnvzqvHu7Ur
TkXWStAmzOVyyghqpZXjFaH3pO3JLF+l+/+sKAIuvtd7u+Nxe5AW0wdeRlN8NwdC
jNPElpzVmbUq4JUagEiuTDkHzsxHpFKVK7q4+63SM1N95R1NbdWhscdCb+ZAJzVc
oyi3B43njTOQ5yOf+1CceWxG1bQVs5ZufpsMljq4Ui0/1lvh+wjChP4kqKOJ2qxq
4RgqsahDYVvTH9w7jXbyLeiNdd8XM2w9U/t7y0Ff/9yi0GE44Za4rF2LN9d11TPA
mRGunUHBcnWEvgJBQl9nJEiU0Zsnvgc/ubhPgXRR4Xq37Z0j4r7g1SgEEzwxA57d
emyPxgcYxn/eR44/KJ4EBs+lVDR3veyJm+kXQ99b21/+jh5Xos1AnX5iItreGCc=
-----END CERTIFICATE-----
)EOF";

// ============================================================
//  PIN DEFINITIONS
// ============================================================
#define OLED_SDA      8
#define OLED_SCL      9
#define BUTTON_PIN    7

// INMP441 microphone (I2S_NUM_0)
#define MIC_SCK_PIN   14   // SCK / BCLK
#define MIC_WS_PIN    15   // WS  / LRCLK
#define MIC_SD_PIN    16   // SD  / DIN (data from mic)

// MAX98357 amplifier (I2S_NUM_1)
#define AMP_BCLK_PIN  4    // BCLK
#define AMP_LRC_PIN   5    // LRC / LRCLK
#define AMP_DIN_PIN   6    // DIN (data to amp)

// ============================================================
//  AUDIO CONFIG
// ============================================================
#define I2S_SAMPLE_RATE    16000
#define RECORD_SECONDS     6
#define RECORD_BUFFER_SIZE (I2S_SAMPLE_RATE * RECORD_SECONDS * 2)  // 16-bit = 2 bytes/sample

// ============================================================
//  OLED
// ============================================================
#define SCREEN_WIDTH  128
#define SCREEN_HEIGHT 64
Adafruit_SSD1306 display(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, -1);

// ============================================================
//  STATE
// ============================================================
enum NeshExpression {
  FACE_IDLE,
  FACE_LISTENING,
  FACE_THINKING,
  FACE_SPEAKING,
  FACE_ERROR,
  FACE_NO_WIFI
};

uint8_t* audioBuffer = nullptr;

// ============================================================
//  FACE RENDERER — each expression is distinct
// ============================================================
void drawFace(NeshExpression expr) {
  if (!OLED_ENABLED) return;
  display.clearDisplay();

  int leftEyeX  = 40;
  int rightEyeX = 88;
  int eyeY      = 22;

  switch (expr) {

    case FACE_IDLE:
      // Calm oval eyes + gentle smile
      display.fillRoundRect(leftEyeX - 9,  eyeY - 12, 18, 24, 8, SSD1306_WHITE);
      display.fillRoundRect(rightEyeX - 9, eyeY - 12, 18, 24, 8, SSD1306_WHITE);
      display.drawFastHLine(52, 48, 24, SSD1306_WHITE);
      display.drawPixel(51, 47, SSD1306_WHITE);
      display.drawPixel(50, 46, SSD1306_WHITE);
      display.drawPixel(76, 47, SSD1306_WHITE);
      display.drawPixel(77, 46, SSD1306_WHITE);
      break;

    case FACE_LISTENING:
      // Wide circle eyes (attentive) + neutral flat mouth
      display.drawCircle(leftEyeX,  eyeY, 12, SSD1306_WHITE);
      display.drawCircle(rightEyeX, eyeY, 12, SSD1306_WHITE);
      display.fillCircle(leftEyeX,  eyeY, 5, SSD1306_WHITE);
      display.fillCircle(rightEyeX, eyeY, 5, SSD1306_WHITE);
      display.drawFastHLine(50, 50, 28, SSD1306_WHITE);
      break;

    case FACE_THINKING:
      // Squinting eyes (half-closed) + mouth tilted right (pondering)
      display.fillRoundRect(leftEyeX - 9,  eyeY - 3, 18, 7, 3, SSD1306_WHITE);
      display.fillRoundRect(rightEyeX - 9, eyeY - 3, 18, 7, 3, SSD1306_WHITE);
      // Tilted "hmm" mouth
      display.drawLine(50, 52, 64, 49, SSD1306_WHITE);
      display.drawLine(64, 49, 78, 51, SSD1306_WHITE);
      // Thought dots top-right
      display.fillCircle(100, 14, 2, SSD1306_WHITE);
      display.fillCircle(108, 8,  2, SSD1306_WHITE);
      display.fillCircle(118, 3,  2, SSD1306_WHITE);
      break;

    case FACE_SPEAKING:
      // Normal oval eyes + animated open mouth (circle)
      display.fillRoundRect(leftEyeX - 9,  eyeY - 10, 18, 20, 7, SSD1306_WHITE);
      display.fillRoundRect(rightEyeX - 9, eyeY - 10, 18, 20, 7, SSD1306_WHITE);
      display.drawCircle(64, 50, 8, SSD1306_WHITE);
      display.fillCircle(64, 50, 5, SSD1306_WHITE);
      break;

    case FACE_ERROR:
      // X eyes + frown
      // Left X
      display.drawLine(leftEyeX - 8,  eyeY - 8, leftEyeX + 8,  eyeY + 8, SSD1306_WHITE);
      display.drawLine(leftEyeX + 8,  eyeY - 8, leftEyeX - 8,  eyeY + 8, SSD1306_WHITE);
      // Right X
      display.drawLine(rightEyeX - 8, eyeY - 8, rightEyeX + 8, eyeY + 8, SSD1306_WHITE);
      display.drawLine(rightEyeX + 8, eyeY - 8, rightEyeX - 8, eyeY + 8, SSD1306_WHITE);
      // Frown
      display.drawFastHLine(52, 50, 24, SSD1306_WHITE);
      display.drawPixel(51, 51, SSD1306_WHITE);
      display.drawPixel(50, 52, SSD1306_WHITE);
      display.drawPixel(76, 51, SSD1306_WHITE);
      display.drawPixel(77, 52, SSD1306_WHITE);
      break;

    case FACE_NO_WIFI:
      // Sad droopy eyes + frown + WiFi-off icon
      display.fillRoundRect(leftEyeX - 9,  eyeY - 8, 18, 16, 6, SSD1306_WHITE);
      display.fillRoundRect(rightEyeX - 9, eyeY - 8, 18, 16, 6, SSD1306_WHITE);
      display.drawFastHLine(52, 50, 24, SSD1306_WHITE);
      display.drawPixel(51, 51, SSD1306_WHITE);
      display.drawPixel(50, 52, SSD1306_WHITE);
      display.drawPixel(76, 51, SSD1306_WHITE);
      display.drawPixel(77, 52, SSD1306_WHITE);
      // Small WiFi-X icon bottom-right
      display.drawLine(110, 58, 118, 58, SSD1306_WHITE);
      display.drawLine(110, 54, 118, 62, SSD1306_WHITE);
      display.drawLine(118, 54, 110, 62, SSD1306_WHITE);
      break;
  }

  display.display();
}

// ============================================================
//  STATUS HELPER — draws face + text on bottom line
// ============================================================
void showStatus(NeshExpression expr, const char* message) {
  drawFace(expr);
  if (OLED_ENABLED) {
    display.setTextSize(1);
    display.setTextColor(SSD1306_WHITE);
    display.setCursor(0, 56);
    display.println(message);
    display.display();
  }
  Serial.print("[STATUS] ");
  Serial.println(message);
}

// ============================================================
//  WiFi
// ============================================================
void connectWiFi() {
  showStatus(FACE_NO_WIFI, "Connecting WiFi...");
  WiFi.mode(WIFI_STA);
  WiFi.disconnect(true);
  delay(500);

  // --- DIAGNOSTIC: list every 2.4GHz network the ESP32 can actually see ---
  Serial.println("[WiFi] Scanning for networks...");
  int found = WiFi.scanNetworks();
  if (found == 0) {
    Serial.println("[WiFi] Scan found NO networks at all.");
  } else {
    bool targetSeen = false;
    for (int i = 0; i < found; i++) {
      String ssid = WiFi.SSID(i);
      Serial.printf("[WiFi] Seen: \"%s\" (RSSI %d)\n", ssid.c_str(), WiFi.RSSI(i));
      if (ssid == String(WIFI_SSID)) targetSeen = true;
    }
    Serial.print("[WiFi] Target SSID \"");
    Serial.print(WIFI_SSID);
    Serial.println(targetSeen ? "\" WAS found in scan." : "\" was NOT found in scan.");
  }
  WiFi.scanDelete();
  // --- end diagnostic ---

  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 30) {
    delay(500);
    Serial.print(".");
    attempts++;
    yield();
  }
  Serial.println();

  if (WiFi.status() == WL_CONNECTED) {
    Serial.print("[WiFi] Connected. IP: ");
    Serial.println(WiFi.localIP());
    syncTime();
    showStatus(FACE_IDLE, "WiFi OK!");
    delay(500);
  } else {
    Serial.println("[WiFi] ERROR: Failed to connect after 30 attempts.");
    Serial.print("[WiFi] Last status code: ");
    Serial.println(WiFi.status());
    showStatus(FACE_NO_WIFI, "WiFi Failed!");
  }
}

// ============================================================
//  NTP TIME SYNC
//  Required before any TLS handshake: WiFiClientSecure validates
//  the pinned root CA's notBefore/notAfter against the system
//  clock. Without this, the ESP32 boots at epoch 0 (1970) and
//  every TLS connect() fails with a generic "TLS connect failed".
// ============================================================
void syncTime() {
  showStatus(FACE_THINKING, "Syncing time...");
  configTime(0, 0, "pool.ntp.org", "time.nist.gov");

  Serial.print("[TIME] Waiting for NTP sync");
  time_t now = time(nullptr);
  int attempts = 0;
  while (now < 8 * 3600 * 2 && attempts < 40) { // wait until well past epoch
    delay(250);
    Serial.print(".");
    now = time(nullptr);
    attempts++;
    yield();
  }
  Serial.println();

  if (now < 8 * 3600 * 2) {
    Serial.println("[TIME] ERROR: NTP sync failed. TLS requests will likely fail.");
  } else {
    struct tm timeinfo;
    gmtime_r(&now, &timeinfo);
    Serial.print("[TIME] Synced: ");
    Serial.print(asctime(&timeinfo));
  }
}

// ============================================================
//  I2S MICROPHONE INIT (I2S_NUM_0)
// ============================================================
void initMicrophoneI2S() {
  i2s_config_t cfg = {
    .mode                 = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_RX),
    .sample_rate          = I2S_SAMPLE_RATE,
    .bits_per_sample      = I2S_BITS_PER_SAMPLE_16BIT,
    .channel_format       = I2S_CHANNEL_FMT_ONLY_LEFT,
    .communication_format = I2S_COMM_FORMAT_STAND_I2S,
    .intr_alloc_flags     = ESP_INTR_FLAG_LEVEL1,
    .dma_buf_count        = 8,
    .dma_buf_len          = 256,
    .use_apll             = false
  };

  i2s_pin_config_t pins = {
    .bck_io_num   = MIC_SCK_PIN,
    .ws_io_num    = MIC_WS_PIN,
    .data_out_num = I2S_PIN_NO_CHANGE,
    .data_in_num  = MIC_SD_PIN
  };

  esp_err_t err = i2s_driver_install(I2S_NUM_0, &cfg, 0, NULL);
  if (err != ESP_OK) {
    Serial.print("[MIC] ERROR: i2s_driver_install failed: ");
    Serial.println(esp_err_to_name(err));
  }

  err = i2s_set_pin(I2S_NUM_0, &pins);
  if (err != ESP_OK) {
    Serial.print("[MIC] ERROR: i2s_set_pin failed: ");
    Serial.println(esp_err_to_name(err));
  }

  i2s_stop(I2S_NUM_0);
  Serial.println("[MIC] I2S microphone initialised (I2S_NUM_0).");
}

// ============================================================
//  RECORD AUDIO
//  Returns bytes recorded (0 on failure)
// ============================================================
size_t recordAudio() {
  Serial.println("[MIC] Starting recording...");
  i2s_start(I2S_NUM_0);
  i2s_zero_dma_buffer(I2S_NUM_0);

  size_t totalBytesRead = 0;
  size_t bytesRead      = 0;
  unsigned long startTime = millis();
  unsigned long deadline  = RECORD_SECONDS * 1000UL + 500UL;

  while (totalBytesRead < RECORD_BUFFER_SIZE && (millis() - startTime) < deadline) {
    size_t remaining  = RECORD_BUFFER_SIZE - totalBytesRead;
    size_t chunkSize  = remaining > 1024 ? 1024 : remaining;

    esp_err_t result = i2s_read(I2S_NUM_0, audioBuffer + totalBytesRead,
                                chunkSize, &bytesRead, portMAX_DELAY);
    if (result == ESP_OK) {
      totalBytesRead += bytesRead;
    } else {
      Serial.print("[MIC] ERROR: i2s_read failed: ");
      Serial.println(esp_err_to_name(result));
      break;
    }
    yield();
  }

  i2s_stop(I2S_NUM_0);

  if (totalBytesRead == 0) {
    Serial.println("[MIC] ERROR: Zero bytes recorded. Check INMP441 wiring on pins 14/15/16.");
  } else {
    Serial.print("[MIC] Recorded ");
    Serial.print(totalBytesRead);
    Serial.println(" bytes.");
  }

  return totalBytesRead;
}

// ============================================================
//  WAV HEADER
// ============================================================
void writeWavHeader(uint8_t* header, size_t dataSize) {
  uint32_t fileSize    = dataSize + 36;
  uint32_t sampleRate  = I2S_SAMPLE_RATE;
  uint16_t bitsPerSamp = 16;
  uint16_t numChannels = 1;
  uint32_t byteRate    = sampleRate * numChannels * bitsPerSamp / 8;
  uint16_t blockAlign  = numChannels * bitsPerSamp / 8;
  uint32_t fmtSize     = 16;
  uint16_t audioFormat = 1; // PCM

  memcpy(header,      "RIFF",       4);
  memcpy(header + 4,  &fileSize,    4);
  memcpy(header + 8,  "WAVE",       4);
  memcpy(header + 12, "fmt ",       4);
  memcpy(header + 16, &fmtSize,     4);
  memcpy(header + 20, &audioFormat, 2);
  memcpy(header + 22, &numChannels, 2);
  memcpy(header + 24, &sampleRate,  4);
  memcpy(header + 28, &byteRate,    4);
  memcpy(header + 32, &blockAlign,  2);
  memcpy(header + 34, &bitsPerSamp, 2);
  memcpy(header + 36, "data",       4);
  memcpy(header + 40, &dataSize,    4);
}

// ============================================================
//  VOLUME SCALER
// ============================================================
void applyVolumeScale(int16_t* samples, size_t sampleCount, float volume) {
  for (size_t i = 0; i < sampleCount; i++) {
    int32_t scaled = (int32_t)(samples[i] * volume);
    if (scaled >  32767) scaled =  32767;
    if (scaled < -32768) scaled = -32768;
    samples[i] = (int16_t)scaled;
  }
}

// ============================================================
//  PLAY RAW PCM STREAM via I2S_NUM_1 (MAX98357 amp)
//
//  NOTE: The backend returns raw 16-bit PCM at 16 kHz,
//  NOT an MP3. No MP3 decoder is present or needed.
//  If the backend ever switches to MP3, add an MP3 decoder
//  library (e.g. libhelix-mp3) before calling i2s_write.
//
//  contentLength = -1 means the server sent no Content-Length;
//  we fall back to reading until the connection drops.
// ============================================================
static bool ampInstalled = false;

void playPcmStream(WiFiClient* stream, int contentLength) {
  i2s_config_t cfg = {
    .mode                 = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_TX),
    .sample_rate          = I2S_SAMPLE_RATE,
    .bits_per_sample      = I2S_BITS_PER_SAMPLE_16BIT,
    .channel_format       = I2S_CHANNEL_FMT_ONLY_LEFT,
    .communication_format = I2S_COMM_FORMAT_STAND_I2S,
    .intr_alloc_flags     = ESP_INTR_FLAG_LEVEL1,
    .dma_buf_count        = 8,
    .dma_buf_len          = 256,
    .use_apll             = false,
    .tx_desc_auto_clear   = true
  };

  i2s_pin_config_t pins = {
    .bck_io_num   = AMP_BCLK_PIN,
    .ws_io_num    = AMP_LRC_PIN,
    .data_out_num = AMP_DIN_PIN,
    .data_in_num  = I2S_PIN_NO_CHANGE
  };

  if (!ampInstalled) {
    esp_err_t err = i2s_driver_install(I2S_NUM_1, &cfg, 0, NULL);
    if (err != ESP_OK) {
      Serial.print("[AMP] ERROR: i2s_driver_install failed: ");
      Serial.println(esp_err_to_name(err));
      return;
    }
    err = i2s_set_pin(I2S_NUM_1, &pins);
    if (err != ESP_OK) {
      Serial.print("[AMP] ERROR: i2s_set_pin failed: ");
      Serial.println(esp_err_to_name(err));
      return;
    }
    ampInstalled = true;
    Serial.println("[AMP] I2S amplifier initialised (I2S_NUM_1).");
  } else {
    i2s_start(I2S_NUM_1);
  }

  uint8_t buffer[512];
  size_t  bytesWritten = 0;
  int     totalRead    = 0;
  bool    streaming    = (contentLength == -1);

  Serial.print("[AMP] Playing PCM. Content-Length: ");
  if (streaming) Serial.println("unknown (streaming until close)");
  else           Serial.println(contentLength);

  while (stream->connected()) {
    if (!streaming && totalRead >= contentLength) break;

    if (stream->available()) {
      int len = stream->readBytes(buffer, sizeof(buffer));
      if (len <= 0) {
        Serial.println("[AMP] WARN: readBytes returned 0. Stream may have ended early.");
        break;
      }
      applyVolumeScale((int16_t*)buffer, len / 2, SPEAKER_VOLUME);

      esp_err_t err = i2s_write(I2S_NUM_1, buffer, len, &bytesWritten, portMAX_DELAY);
      if (err != ESP_OK) {
        Serial.print("[AMP] ERROR: i2s_write failed: ");
        Serial.println(esp_err_to_name(err));
        break;
      }
      totalRead += len;
    } else {
      // Small yield while waiting for more data
      delay(2);
    }
    yield();
  }

  i2s_stop(I2S_NUM_1);
  Serial.print("[AMP] Playback complete. Total bytes played: ");
  Serial.println(totalRead);
}

// ============================================================
//  SEND AUDIO → SERVER, PLAY RESPONSE
// ============================================================
bool sendAudioAndPlayResponse(size_t audioDataSize) {
  // --- Parse URL ---
  String fullUrl  = String(SERVER_URL);
  int    protoEnd = fullUrl.indexOf("://") + 3;
  String hostPart = fullUrl.substring(protoEnd);
  String host     = hostPart.substring(0, hostPart.indexOf('/'));
  String path     = hostPart.substring(hostPart.indexOf('/'));
  path += "?stream="     + String(STREAM)
       + "&subject="     + String(SUBJECT)
       + "&medium="      + String(MEDIUM)
       + "&student_id="  + String(STUDENT_ID);

  Serial.print("[HTTP] Connecting to host: ");
  Serial.println(host);
  Serial.print("[HTTP] Path: ");
  Serial.println(path);

  // --- TLS with root CA verification ---
  WiFiClientSecure secureClient;
  secureClient.setCACert(ROOT_CA);
  secureClient.setTimeout(30);

  if (!secureClient.connect(host.c_str(), 443)) {
    Serial.println("[HTTP] ERROR: TLS connect failed. Check root CA or host.");
    return false;
  }
  Serial.println("[HTTP] TLS connected.");

  // --- Build multipart body ---
  String boundary  = "----ObscuraBoundary7MA4YWxk";
  String bodyStart = "--" + boundary
    + "\r\nContent-Disposition: form-data; name=\"audio\"; filename=\"mic.wav\""
    + "\r\nContent-Type: audio/wav\r\n\r\n";
  String bodyEnd   = "\r\n--" + boundary + "--\r\n";

  uint8_t wavHeader[44];
  writeWavHeader(wavHeader, audioDataSize);

  size_t contentLengthOut = bodyStart.length() + 44 + audioDataSize + bodyEnd.length();

  Serial.print("[HTTP] Sending POST, body size: ");
  Serial.print(contentLengthOut);
  Serial.println(" bytes.");

  secureClient.print(
    String("POST ") + path + " HTTP/1.1\r\n"
    "Host: " + host + "\r\n"
    "Content-Type: multipart/form-data; boundary=" + boundary + "\r\n"
    "Content-Length: " + String(contentLengthOut) + "\r\n"
    "Connection: close\r\n\r\n"
  );
  secureClient.print(bodyStart);
  secureClient.write(wavHeader, 44);

  size_t sent = 0;
  while (sent < audioDataSize) {
    size_t toSend = min((size_t)1024, audioDataSize - sent);
    size_t written = secureClient.write(audioBuffer + sent, toSend);
    if (written == 0) {
      Serial.println("[HTTP] ERROR: Socket write returned 0 mid-upload. Connection dropped?");
      return false;
    }
    sent += written;
    yield();
  }
  secureClient.print(bodyEnd);
  Serial.println("[HTTP] Upload complete. Waiting for response...");

  // --- Wait for response headers ---
  unsigned long startWait = millis();
  while (!secureClient.available() && millis() - startWait < 30000) {
    delay(10);
    yield();
  }
  if (!secureClient.available()) {
    Serial.println("[HTTP] ERROR: Server did not respond within 30s.");
    return false;
  }

  // --- Parse status line ---
  String statusLine = secureClient.readStringUntil('\n');
  statusLine.trim();
  Serial.print("[HTTP] Response: ");
  Serial.println(statusLine);

  if (statusLine.indexOf("200") < 0) {
    Serial.print("[HTTP] ERROR: Non-200 status. Full status: ");
    Serial.println(statusLine);
    // Drain body for debugging
    while (secureClient.available()) {
      String errBody = secureClient.readStringUntil('\n');
      errBody.trim();
      if (errBody.length() > 0) Serial.println("[HTTP] Body: " + errBody);
    }
    return false;
  }

  // --- Parse headers ---
  int responseContentLength = -1;
  while (true) {
    String line = secureClient.readStringUntil('\n');
    line.trim();
    if (line.length() == 0) break; // blank line = end of headers
    Serial.print("[HTTP] Header: ");
    Serial.println(line);
    if (line.startsWith("Content-Length:")) {
      responseContentLength = line.substring(15).toInt();
      Serial.print("[HTTP] Content-Length parsed: ");
      Serial.println(responseContentLength);
    }
  }

  if (responseContentLength == -1) {
    Serial.println("[HTTP] WARN: No Content-Length header. Will stream until connection closes.");
  }

  // --- Play response ---
  showStatus(FACE_SPEAKING, "NESH Speaking...");
  playPcmStream(&secureClient, responseContentLength);
  return true;
}

// ============================================================
//  MAIN INTERACTION
// ============================================================
void handleVoiceInteraction() {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("[MAIN] WiFi not connected. Reconnecting...");
    showStatus(FACE_NO_WIFI, "Reconnecting...");
    connectWiFi();
    if (WiFi.status() != WL_CONNECTED) return;
  }

  showStatus(FACE_LISTENING, "Listening...");
  size_t recordedBytes = recordAudio();

  if (recordedBytes == 0) {
    Serial.println("[MAIN] ERROR: recordAudio() returned 0 bytes.");
    showStatus(FACE_ERROR, "Mic Error");
    delay(2000);
    showStatus(FACE_IDLE, "NESH Ready");
    return;
  }

  showStatus(FACE_THINKING, "Thinking...");
  if (sendAudioAndPlayResponse(recordedBytes)) {
    Serial.println("[MAIN] Interaction complete.");
    showStatus(FACE_IDLE, "NESH Ready");
  } else {
    Serial.println("[MAIN] ERROR: sendAudioAndPlayResponse() failed.");
    showStatus(FACE_ERROR, "Error");
    delay(2000);
    showStatus(FACE_IDLE, "NESH Ready");
  }
}

// ============================================================
//  SETUP
// ============================================================
void setup() {
  Serial.begin(115200);
  delay(300);
  Serial.println("\n\n========================================");
  Serial.println(" OBSCURA NESH — Boot");
  Serial.println("========================================");

  pinMode(BUTTON_PIN, INPUT_PULLUP);

  if (OLED_ENABLED) {
    Wire.begin(OLED_SDA, OLED_SCL);
    if (!display.begin(SSD1306_SWITCHCAPVCC, 0x3C)) {
      Serial.println("[OLED] ERROR: SSD1306 not found at 0x3C. Check SDA/SCL on pins 8/9.");
    } else {
      Serial.println("[OLED] Display initialised.");
      display.clearDisplay();
      display.display();
    }
  }

  showStatus(FACE_THINKING, "Booting...");

  // Allocate recording buffer — FATAL if it fails
  audioBuffer = (uint8_t*) malloc(RECORD_BUFFER_SIZE);
  if (audioBuffer == NULL) {
    Serial.println("[MAIN] FATAL: malloc failed for audio buffer.");
    Serial.print("[MAIN] Requested: ");
    Serial.print(RECORD_BUFFER_SIZE);
    Serial.println(" bytes. Not enough heap.");
    Serial.print("[MAIN] Free heap: ");
    Serial.println(ESP.getFreeHeap());
    showStatus(FACE_ERROR, "RAM Error");
    while (true) delay(1000); // Hard halt — do not proceed without buffer
  }
  Serial.print("[MAIN] Audio buffer allocated: ");
  Serial.print(RECORD_BUFFER_SIZE);
  Serial.println(" bytes.");
  Serial.print("[MAIN] Free heap after malloc: ");
  Serial.println(ESP.getFreeHeap());

  initMicrophoneI2S();
  delay(100);
  yield();

  connectWiFi();

  showStatus(FACE_IDLE, "NESH Ready");
  Serial.println("[MAIN] Boot complete. Press button to speak.");
}

// ============================================================
//  LOOP
// ============================================================
void loop() {
  static int lastSwitchState = HIGH;
  int currentSwitchState = digitalRead(BUTTON_PIN);

  if (currentSwitchState == LOW && lastSwitchState == HIGH) {
    delay(50); // debounce
    if (digitalRead(BUTTON_PIN) == LOW) {
      Serial.println("\n[MAIN] Button pressed.");
      handleVoiceInteraction();
    }
  }

  lastSwitchState = currentSwitchState;
  delay(20);
  yield();
}
