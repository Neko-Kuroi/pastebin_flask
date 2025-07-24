from flask import Flask, request, render_template, abort, flash, redirect, url_for
import shortuuid
import os
from pygments import highlight

# 修正後
from pygments.lexers import get_lexer_by_name, get_all_lexers
from pygments.util import ClassNotFound
from pygments.formatters import HtmlFormatter
import logging

# ロギングを設定
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

app = Flask(__name__)
# フラッシュメッセージのためにシークレットキーを設定
# generate_secret_key.py
import secrets
# 32バイト（256ビット）のキーを生成
secret_key = secrets.token_hex(32)
#print(f"FLASK_SECRET_KEY='{secret_key}'")
app.secret_key = secret_key #os.environ.get('FLASK_SECRET_KEY', 'supersecretkey_for_dev_only')

# ペーストファイルを保存するディレクトリ
PASTE_DIR = 'pastes'
if not os.path.exists(PASTE_DIR):
    try:
        os.makedirs(PASTE_DIR)
        logging.info(f"ディレクトリ '{PASTE_DIR}' を作成しました。")
    except OSError as e:
        logging.error(f"ディレクトリ '{PASTE_DIR}' の作成中にエラーが発生しました: {e}")
        # アプリケーションがディレクトリなしで起動できない場合、ここで終了するかもしれません
        # ただし、開発環境では続行することが多いです

# 利用可能なプログラミング言語オプションをキャッシュする
_language_options_cache = None

def get_language_options():
    """
    Pygmentsから利用可能なプログラミング言語オプションのリストを取得し、キャッシュします。
    戻り値:
        list: (言語エイリアス, 言語名) のタプルのソートされたリスト。
    """
    global _language_options_cache
    if _language_options_cache is None:
        # Pygmentsがサポートするすべてのレクサーを取得し、エイリアスと名前のタプルを生成
        _language_options_cache = sorted([(lexer[1][0], lexer[0]) for lexer in get_all_lexers() if lexer[1]])
        logging.info("言語オプションのキャッシュを初期化しました。")
    return _language_options_cache

# メインページのルート
@app.route('/', methods=['GET', 'POST'])
def index():
    """
    ペーストの作成フォームを表示し、新しいペーストを処理します。
    POSTリクエストの場合、コンテンツを保存し、新しいペーストのURLを生成します。
    GETリクエストの場合、ペースト作成フォームを表示します。
    """
    if request.method == 'POST':
        content = request.form.get('content')
        language = request.form.get('language')

        if not content:
            flash('ペーストするコンテンツを入力してください。', 'error')
            return render_template('index.html', languages=get_language_options())
        if not language:
            flash('言語を選択してください。', 'error')
            return render_template('index.html', languages=get_language_options())

        paste_id = shortuuid.uuid()
        file_path = os.path.join(PASTE_DIR, paste_id)

        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(f"{language}\n{content}")
            paste_url = url_for('view_paste', paste_id=paste_id, _external=True)
            flash(f'ペーストが正常に作成されました！', 'success')
            # 新しいペーストのURLを直接表示する代わりに、リダイレクトしてフラッシュメッセージを表示
            return redirect(paste_url)
        except IOError as e:
            logging.error(f"ペーストID {paste_id} のファイル書き込み中にエラーが発生しました: {e}")
            flash('ペーストの保存中にエラーが発生しました。', 'error')
            return render_template('index.html', languages=get_language_options())

    return render_template('index.html', languages=get_language_options())

# 特定のペーストをIDで表示するルート
@app.route('/<paste_id>')
def view_paste(paste_id):
    """
    指定されたIDのペーストを表示します。
    ペーストが存在しない場合、404エラーを返します。
    コンテンツをシンタックスハイライトして表示します。
    引数:
        paste_id (str): 表示するペーストのユニークID。
    """
    file_path = os.path.join(PASTE_DIR, paste_id)

    if not os.path.exists(file_path):
        logging.warning(f"ペーストID {paste_id} が見つかりませんでした。")
        abort(404)

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            language = f.readline().strip()
            content = f.read()
    except IOError as e:
        logging.error(f"ペーストID {paste_id} のファイル読み込み中にエラーが発生しました: {e}")
        flash('ペーストの読み込み中にエラーが発生しました。', 'error')
        abort(500) # 内部サーバーエラー

    highlighted_content = ""
    highlight_css = ""
    try:
        lexer = get_lexer_by_name(language, stripall=True)
        formatter = HtmlFormatter(linenos=True, cssclass="source")
        highlighted_content = highlight(content, lexer, formatter)
        highlight_css = formatter.get_style_defs('.source')
    #except LexerNotFound:
    except ClassNotFound:
        logging.warning(f"不明な言語 '{language}' のレクサーが見つかりませんでした。ハイライトなしで表示します。")
        # 言語が見つからない場合は、ハイライトなしでコンテンツをそのまま表示
        highlighted_content = f"<pre class='source'>{content}</pre>"
        highlight_css = "" # カスタムCSSは不要

    return render_template('index.html', paste_content=highlighted_content, highlight_css=highlight_css, paste_id=paste_id)

# カスタム404エラーハンドラ
@app.errorhandler(404)
def page_not_found(error):
    """
    404 Not Found エラーが発生したときに表示されるカスタムページ。
    """
    return render_template('404.html'), 404

if __name__ == '__main__':
    # 開発環境でのみ、FLASK_SECRET_KEYが設定されていない場合にデフォルト値を使用
    if os.environ.get('FLASK_ENV') == 'development' and not os.environ.get('FLASK_SECRET_KEY'):
        logging.warning("環境変数 'FLASK_SECRET_KEY' が設定されていません。開発目的でのみ使用してください。")
    app.run(debug=True, host="0.0.0.0", port=5000)
