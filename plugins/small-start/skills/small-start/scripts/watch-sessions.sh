#!/bin/bash
# small-start の見張り: 担当セッションのターン終了と当日のデプロイを待ち、最初の出来事を出して終わる（最長 4 時間）。
# 使い方（Bash の run_in_background で、リポジトリの中から）:
#   bash watch-sessions.sh <sessions.tsv> [tag-regex]
#   sessions.tsv: 1 行 1 セッション「名前<TAB>transcript の jsonl のパス」（~ 可）
#   tag-regex: 例 '^(stg|prod)-v20261105'。省略するとデプロイは見ない
# 出来事が起きたら 1 回だけ出して終わるので、前台はそのたびに起動し直す。
LIST="$1"
TAGRE="${2:-}"
STATE="$(cd "$(dirname "$LIST")" && pwd)"
NAMES=()
FILES=()
while IFS=$'\t' read -r n f; do
  [ -n "$n" ] && NAMES+=("$n") && FILES+=("${f/#\~/$HOME}")
done < "$LIST"

# ターンの終わり = stop_hook_summary（Desktop のセッションは turn_duration を書かない）
# ターンの後にも行が増え続けることがあるので、2000 行さかのぼって探す
last_turn() {
  tail -n 2000 "$1" 2>/dev/null | grep '"subtype":"stop_hook_summary"' | tail -n 1 | jq -r '.timestamp // empty' 2>/dev/null
}

# 最後の回答の先頭 400 字（これで足りるようにして、前台が transcript を読み直さずに済むようにする）
last_text() {
  tail -n 2000 "$1" 2>/dev/null \
    | jq -c 'select(.type=="assistant") | [.message.content[]? | select(.type=="text") | .text] | join(" ") | select(length>0)' 2>/dev/null \
    | tail -n 1 | jq -r 'gsub("\n";" ") | gsub("\\*\\*";"") | .[0:400]' 2>/dev/null
}

deploys() {
  [ -z "$TAGRE" ] && return
  gh api 'repos/{owner}/{repo}/actions/runs?per_page=15' \
    --jq ".workflow_runs[] | select(.head_branch | test(\"$TAGRE\")) | \"\(.head_branch) \(.status) \(.conclusion // \"-\")\"" 2>/dev/null | sort
}

# 状態ファイルはセッション名で引く（sessions.tsv の並びが変わっても取り違えない）
key() { printf '%s' "$1" | { shasum 2>/dev/null || sha1sum; } | cut -c1-12; }

# 起点は前回の見張りから引き継ぐ。起動し直すあいだに終わったターンも取りこぼさない
for i in "${!FILES[@]}"; do
  kf="$STATE/.watch-last-$(key "${NAMES[$i]}")"
  if [ -s "$kf" ]; then
    LAST[$i]=$(cat "$kf")
  else
    LAST[$i]=$(last_turn "${FILES[$i]}")
    printf '%s' "${LAST[$i]}" > "$kf"
  fi
done
PREV=$(deploys)
END=$(( $(date +%s) + 4 * 3600 ))
n=0
while [ "$(date +%s)" -lt "$END" ]; do
  OUT=""
  for i in "${!FILES[@]}"; do
    t=$(last_turn "${FILES[$i]}")
    if [ -n "$t" ] && [ "$t" != "${LAST[$i]}" ]; then
      LAST[$i]=$t
      printf '%s' "$t" > "$STATE/.watch-last-$(key "${NAMES[$i]}")"
      txt=$(last_text "${FILES[$i]}")
      # 途中経過だけの回は出さない（質問があれば出す）
      # 「退回」だけだと、結果報告の「退回：」（戻し方の節）まで飛ばしてしまうので、差し戻しの言い方に絞る
      if printf '%s' "$txt" | grep -qiE "still running|still going|hasn.t reported|sent it back|one more round|another round|review is running|还在跑|还在等|被退回|退回了|退回重做|打回" && ! printf '%s' "$txt" | grep -q "Question"; then
        continue
      fi
      # 同じ質問のくり返しは出さない
      q=$(printf '%s' "$txt" | grep -o "Question:.*" | head -c 200)
      qf="$STATE/.watch-lastq-$(key "${NAMES[$i]}")"
      if [ -n "$q" ] && [ -f "$qf" ] && [ "$q" = "$(cat "$qf")" ]; then
        continue
      fi
      [ -n "$q" ] && printf '%s' "$q" > "$qf"
      OUT="${OUT}[${NAMES[$i]}] $(date '+%H:%M') 一轮结束：${txt}"$'\n'
    fi
  done
  n=$((n + 1))
  if [ $((n % 3)) -eq 0 ]; then
    CUR=$(deploys)
    if [ -n "$CUR" ]; then
      D2=$(comm -13 <(echo "$PREV") <(echo "$CUR") | sed 's/^/[deploy] /')
      [ -n "$D2" ] && OUT="${OUT}${D2}"$'\n'
      PREV=$CUR
    fi
  fi
  if [ -n "$OUT" ]; then printf '%s' "$OUT"; exit 0; fi
  sleep 20
done
echo "[watch] $(date '+%H:%M') 4 小时没有动静，见张结束"
