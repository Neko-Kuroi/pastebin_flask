from flask import Flask, request, render_template, abort, flash, redirect, url_for
import shortuuid
import duckdb
from pygments import highlight
from pygments.lexers import get_lexer_by_name, get_all_lexers
from pygments.util import ClassNotFound
from pygments.formatters import HtmlFormatter
import logging
import os
import atexit # atexitをインポート

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'supersecretkey_for_dev_only')

# Initialize DuckDB connection with persistence
DB_PATH = os.environ.get('DUCKDB_PATH', 'pastes.db')

# DuckDBのデータベースファイルが存在するディレクトリを作成（必要であれば）
# DuckDBはファイル自体を作成しますが、ディレクトリは事前に存在する必要があります
db_dir = os.path.dirname(DB_PATH)
if db_dir and not os.path.exists(db_dir):
    try:
        os.makedirs(db_dir)
        logging.info(f"データベースディレクトリ '{db_dir}' を作成しました。")
    except OSError as e:
        logging.error(f"データベースディレクトリ '{db_dir}' の作成中にエラーが発生しました: {e}")
        raise # ディレクトリがなければデータベース接続も失敗するため、ここで終了

try:
    con = duckdb.connect(DB_PATH)
    logging.info(f"Connected to DuckDB database at {DB_PATH}.")
    
    # Create table for pastes if it doesn't exist
    con.execute("""
        CREATE TABLE IF NOT EXISTS pastes (
            paste_id VARCHAR PRIMARY KEY,
            language VARCHAR NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    logging.info("Initialized 'pastes' table in DuckDB.")
    
except Exception as e:
    logging.error(f"Failed to initialize DuckDB: {e}")
    raise

# Cache for language options
_language_options_cache = None

def get_language_options():
    """
    Retrieve and cache a sorted list of Pygments language options.
    Returns:
        list: Sorted list of (language alias, language name) tuples.
    """
    global _language_options_cache
    if _language_options_cache is None:
        _language_options_cache = sorted([(lexer[1][0], lexer[0]) for lexer in get_all_lexers() if lexer[1]])
        logging.info("Initialized language options cache.")
    return _language_options_cache

@app.route('/', methods=['GET', 'POST'])
def index():
    """
    Display the paste creation form and handle new paste submissions.
    POST: Save content to DuckDB and redirect to the paste's URL.
    GET: Render the paste creation form.
    """
    if request.method == 'POST':
        content = request.form.get('content')
        language = request.form.get('language')

        if not content:
            flash('Please provide content to paste.', 'error')
            return render_template('index.html', languages=get_language_options())
        if not language:
            flash('Please select a language.', 'error')
            return render_template('index.html', languages=get_language_options())

        paste_id = shortuuid.uuid()
        try:
            con.execute(
                "INSERT INTO pastes (paste_id, language, content) VALUES (?, ?, ?)",
                (paste_id, language, content)
            )
            con.commit()  # 明示的にコミット
            logging.info(f"Created paste with ID {paste_id}.")
            flash('Paste created successfully!', 'success')
            return redirect(url_for('view_paste', paste_id=paste_id))
        except Exception as e:
            con.rollback()  # エラー時はロールバック
            logging.error(f"Error saving paste ID {paste_id} to DuckDB: {e}")
            flash('An error occurred while saving the paste.', 'error')
            return render_template('index.html', languages=get_language_options())

    return render_template('index.html', languages=get_language_options())

@app.route('/<paste_id>')
def view_paste(paste_id):
    """
    Display a paste by its ID with syntax highlighting.
    Args:
        paste_id (str): Unique ID of the paste to display.
    """
    # ペーストIDの安全性チェック
    if not paste_id or len(paste_id) > 100:  # reasonable limit
        logging.warning(f"Invalid paste ID format: {paste_id}")
        abort(404)
    
    try:
        result = con.execute(
            "SELECT language, content FROM pastes WHERE paste_id = ?",
            (paste_id,)
        ).fetchone()
        if not result:
            logging.warning(f"Paste ID {paste_id} not found in DuckDB.")
            abort(404)

        language, content = result
    except Exception as e:
        logging.error(f"Error retrieving paste ID {paste_id} from DuckDB: {e}")
        flash('An error occurred while loading the paste.', 'error')
        abort(500)

    highlighted_content = ""
    highlight_css = ""
    try:
        lexer = get_lexer_by_name(language, stripall=True)
        # style='monokai' は削除し、CSSを直接index.htmlに埋め込む
        formatter = HtmlFormatter(linenos=True, cssclass="source")
        highlighted_content = highlight(content, lexer, formatter)
        highlight_css = formatter.get_style_defs('.source') # 行番号などのCSSのみ
    except ClassNotFound:
        logging.warning(f"Unknown language '{language}' for paste ID {paste_id}. Displaying as plain text.")
        from markupsafe import escape
        highlighted_content = f"<pre class='source'>{escape(content)}</pre>"
        highlight_css = ""

    return render_template('index.html', paste_content=highlighted_content, highlight_css=highlight_css, paste_id=paste_id)

@app.errorhandler(404)
def page_not_found(error):
    """
    Custom 404 error page.
    """
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    """
    Custom 500 error page.
    """
    return render_template('500.html'), 500

# アプリケーション終了時のクリーンアップ
def cleanup():
    if 'con' in globals() and con: # conが存在し、Noneでないことを確認
        try:
            con.close()
            logging.info("DuckDB connection closed.")
        except Exception as e:
            logging.error(f"Error closing DuckDB connection: {e}")

atexit.register(cleanup)

if __name__ == '__main__':
    if os.environ.get('FLASK_ENV') == 'development' and not os.environ.get('FLASK_SECRET_KEY'):
        logging.warning("FLASK_SECRET_KEY not set. Using default for development only.")
    app.run(debug=True, host="0.0.0.0", port=5000)

