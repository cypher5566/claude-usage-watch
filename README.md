# Claude Code 用量監看

Claude Code 週額度燒得太快時，用這個找出是哪個分頁、哪個 agent 在背景燒。只讀本機紀錄（`~/.claude/projects`），**不呼叫模型、不花錢、不上傳任何東西**。只支援 macOS。

## 給 Claude Code：使用者請你安裝時，照這幾步做

1. 執行（已裝過會改成更新）：
   `git clone https://github.com/cypher5566/claude-usage-watch ~/.claude-usage-watch 2>/dev/null || git -C ~/.claude-usage-watch pull; ~/.claude-usage-watch/install.sh`
2. 安裝程式最後會印出近 7 天最耗的 5 個分頁。用白話跟使用者說：哪幾個分頁最耗、各花多少、有 ⚠ 的是什麼原因（開了很多 agent、排程／loop、context 很長、開了好幾天沒關），以及建議關掉哪些。金額是照 API 牌價估算，訂閱制不是這樣收費，只用來比大小。
3. 告訴使用者：重開 Claude Code 後，輸入框下方會出現用量狀態列（見下方說明）。
4. 安裝過程不要改其他設定。若出現「找不到 python3」，請使用者自己在終端機執行 `xcode-select --install`，裝好後再跑一次步驟 1。

## 自己安裝（或更新）

在終端機貼：

```bash
git clone https://github.com/cypher5566/claude-usage-watch ~/.claude-usage-watch 2>/dev/null || git -C ~/.claude-usage-watch pull; ~/.claude-usage-watch/install.sh
```

或直接跟 Claude Code 說：「幫我安裝 https://github.com/cypher5566/claude-usage-watch 」。

裝完會馬上印出近 7 天最耗的 5 個分頁，下次開 Claude Code 就會看到狀態列。

## 會得到什麼

**1. 狀態列**（輸入框下方，每 30 秒更新）

```
正常 · 全機近 30 分 ··▁▃▄▄··▂▂▃···▁·▃▃▂▃▂▂▁▁▂·█▆▂▂ US$7.1（門檻 $20，API 價估算）
```

- 算的是**整台電腦**所有 Claude Code 分頁、agent、`claude -p` 加起來，不只眼前這個視窗。
- 近 30 分鐘超過 US$10 變黃（「留意」）、超過 US$20 變紅（「偏高」）；黃或紅時會多一行，標出最耗的是哪個分頁（含它開的 agent）、花了多少，紅的時候提醒用不到就停掉。
- 分頁名稱跟你分頁上看到的一樣：在 Ghostty 自己改過分頁名稱，狀態列就顯示你改的名字；沒改過就用 Claude Code 自動取的標題。其他終端機 App 目前只顯示 Claude Code 的標題。
- 登入失效、用量到上限、斷網、`claude -p` 同時超過 3 個，也會各多一行告訴你怎麼處理。

**用 Claude Desktop 的人**：Desktop 的 Code 分頁裡跑在「這台電腦」的工作階段，一樣會被算進去（紀錄寫在同一個地方）。但 Desktop 不顯示狀態列，所以靠兩樣東西：超過門檻時右上角會跳 macOS 通知「Claude 用量警示」，加上下面的排行報告。

**算不到的**：雲端工作階段（在 Anthropic 的機器上跑）和 Cowork（在虛擬機裡跑），本機沒有紀錄。它們一樣會扣週額度，常用的人看到的數字會偏低。

**2. 近 7 天排行報告**

```bash
python3 ~/.claude/usage-watch/session_usage.py            # 近 7 天
python3 ~/.claude/usage-watch/session_usage.py --days 1   # 近 1 天
```

每個分頁（含它開的 agent）花多少、佔多少 %、第一句指令、用了哪些 skill，以及 ⚠ 可疑跡象：開了一堆 agent、排程／loop、Monitor、context 很長、開了好幾天沒關。前幾名有 ⚠ 的，多半就是背景燒掉的那個；用 `claude --resume <session>` 打開看它在做什麼，不需要就關掉。

## 金額怎麼算

照 Anthropic 官方 API 牌價換算成 USD（`pricing.py`：按模型；input、output、cache 讀取、cache 寫入 5 分鐘／1 小時各自的單價）。**訂閱制不是這樣收費**，這個數字只用來比大小、抓異常。跟 Claude Code 自己記的金額比對過，差距在幾 % 內。

## 移除

```bash
~/.claude-usage-watch/uninstall.sh
```
