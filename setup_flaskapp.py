import time
import os
#import hashlib
#import tempfile
import time
import base64
import subprocess
import threading
import sys
import re
from IPython.display import HTML, display
import logging
import requests # Import the requests library

os.system('pip install gunicorn flask')

# ログの設定
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# ログ読み取り関数は削除またはコメントアウト
def read_process_output(process, stream, prefix=""):
    """プロセスの出力をリアルタイムで読み取り、表示する関数"""
    while True:
        line = stream.readline()
        if line:
            print(f"{prefix}{line.strip()}")
        elif process.poll() is not None:
            try:
                remaining = stream.read()
                if remaining:
                     print(f"{prefix}{remaining.strip()}")
            except ValueError:
                 pass
            break
        else:
            time.sleep(0.01)
    try:
        stream.close()
    except Exception as e:
        logger.debug(f"Error closing stream in read_process_output: {e}")


def setup_bore_tunnel():
    """Rust製のboreトンネルの設定"""
    print("🦀 Bore トンネルをセットアップしています...")

    # boreのダウンロードとインストール
    # -nc オプションは、ファイルが既に存在する場合に再ダウンロードしないようにします。
    os.system('sudo wget -nc https://github.com/ekzhang/bore/releases/download/v0.6.0/bore-v0.6.0-x86_64-unknown-linux-musl.tar.gz')
    # ダウンロードしたアーカイブを解凍します。
    os.system('sudo tar -zxvf bore-v0.6.0-x86_64-unknown-linux-musl.tar.gz')
    # 実行権限を付与し部qー、。
    os.system('sudo chmod 764 bore')

    # flaskアプリケーションをバックグラウンドで起動します。
    # stdoutとstderrをsubprocess.PIPEにリダイレクトしない
    print("🚀 flask アプリケーションを起動しています...")
    flask_process = subprocess.Popen(
        ["gunicorn", "--bind", "0.0.0.0:5000", "app:app", "--access-logfile", "-", "--error-logfile", "-"],
        stdout=subprocess.PIPE, # ログ出力しないため削除
        stderr=subprocess.PIPE, # ログ出力しないため削除
        text=True,
        bufsize=1
    )

    #Flaskプロセスの出力を読み取るスレッドは削除
    flask_stdout_thread = threading.Thread(target=read_process_output, args=(flask_process, flask_process.stdout, "[FLASK_OUT] "))
    flask_stderr_thread = threading.Thread(target=read_process_output, args=(flask_process, flask_process.stderr, "[FLASK_ERR] "))
    flask_stdout_thread.daemon = True
    flask_stderr_thread.daemon = True
    flask_stdout_thread.start()
    flask_stderr_thread.start()


    time.sleep(10)  # flaskサーバーが完全に起動するまで少し長めに7秒待ちます。

    # boreトンネルの起動
    print("🌐 bore トンネルを開始しています...")
    # boreをローカルポート5000からbore.pubへのトンネルとして起動します。
    # stdoutとstderrをsubprocess.PIPEにリダイレクトし、テキストモードでキャプチャします。
    bore_process = subprocess.Popen(['./bore', 'local', '5000', '--to', 'bore.pub'],
                                   stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE,
                                   text=True,
                                   bufsize=1 # 行バッファリングを無効にしてリアルタイム出力を試みる
                                   )

    # Boreプロセスの出力を読み取るスレッドは削除
    bore_stdout_thread = threading.Thread(target=read_process_output, args=(bore_process, bore_process.stdout, "[BORE_OUT] "))
    bore_stderr_thread = threading.Thread(target=read_process_output, args=(bore_process, bore_process.stderr, "[BORE_ERR] "))
    bore_stdout_thread.daemon = True
    bore_stderr_thread.daemon = True
    bore_stdout_thread.start()
    bore_stderr_thread.start()


    # トンネルのURLを取得
    print("🔍 トンネルURLを待機しています...")
    url_found = False
    url = ""
    # タイムアウトを設定し、無限ループにならないようにします
    start_time = time.time()
    timeout = 130 # タイムアウト

    # Boreの標準出力からURLを読み取るループは維持（URL表示のため）
    while time.time() - start_time < timeout:
        line = bore_process.stdout.readline()
        if line:
            # print(f"Bore stdout: {line.strip()}") # デバッグ出力は削除
            match = re.search(r'(bore\.pub:\d+)', line)
            if match:
                extracted_url_part = match.group(0).strip()
                url = f"{extracted_url_part}"
                url_found = True
                break

        # boreが終了したか確認（エラーになった場合など）
        if bore_process.poll() is not None:
            print("Boreプロセスが予期せず終了しました。")
            break

        time.sleep(0.1) # 短い間隔で繰り返し確認

    if url_found:
        print(f"✅ トンネルが開始されました: {url}")
        # IPython.display.HTML を使用して、クリック可能なURLを生成し表示します。
        display(HTML(f'<a href="http://{url}" target="_blank" style="font-size:18px; color:pink;">{url}</a>'))
        # boreトンネルへのcurlテスト
        print("\n--- Boreトンネルへの内部curlテスト ---")
        try:
            # 外部からアクセスするURLに対してcurlを実行
            curl_url = f"http://{url}"
            curl_result = subprocess.run(['curl', '-s', '-I', curl_url], capture_output=True, text=True, timeout=10)
            print("curl出力（ヘッダのみ）：")
            print(curl_result.stdout.strip())
            if "200 OK" in curl_result.stdout:
                print("✅ curlテスト成功: HTTP 200 OK を受信しました。ブラウザでアクセスできるはずです。")
            else:
                print("❌ curlテスト失敗: 予期しない応答コードを受信しました。")
                # print(f"Boreの応答全文:\n{curl_result.stdout}\n{curl_result.stderr}") # スレッドが出力済みのため不要
        except subprocess.TimeoutExpired:
            print("❌ curlテスト失敗: タイムアウトしました。Boreサービスが応答していません。")
        except Exception as e:
            print(f"❌ curlテスト中にエラーが発生しました: {e}")
        print("----------------------------")

    else:
        print("⚠️ トンネルURLの取得に失敗しました。")
        # Boreプロセスの標準出力と標準エラー出力の表示は削除
        # print("Boreプロセスの標準出力と標準エラー出力を確認してください。")
        # final_stdout = bore_process.stdout.read()
        # final_stderr = bore_process.stderr.read()
        # if final_stdout:
        #     print(f"最終的なBore stdout: \n{final_stdout.strip()}")
        # if final_stderr:
        #     print(f"最終的なBore stderr: \n{final_stderr.strip()}")

        # スレッドのjoinも不要
        # bore_stdout_thread.join(timeout=5)
        # bore_stderr_thread.join(timeout=5)


    return flask_process, bore_process

def setup_cloudflare_tunnel():
    """Cloudflare Tunnelの設定"""
    print("☁️ Cloudflare Tunnel をセットアップしています...")

    # cloudflaredのダウンロードとインストール
    os.system('sudo wget -nc https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb')
    os.system('sudo dpkg -i cloudflared-linux-amd64.deb 2>/dev/null')

    # flaskアプリケーションをバックグラウンドで起動
    # stdoutとstderrをsubprocess.PIPEにリダイレクトしない
    print("🚀 flask アプリケーションを起動しています...")
    flask_process = subprocess.Popen(
        ["gunicorn", "--bind", "0.0.0.0:5000", "app:app", "--access-logfile", "-", "--error-logfile", "-"],
        stdout=subprocess.PIPE, # ログ出力しないため削除
        stderr=subprocess.PIPE, # ログ出力しないため削除
        text=True,
        bufsize=1
    )

    #Flaskプロセスの出力を読み取るスレッドは削除
    flask_stdout_thread = threading.Thread(target=read_process_output, args=(flask_process, flask_process.stdout, "[FLASK_OUT] "))
    flask_stderr_thread = threading.Thread(target=read_process_output, args=(flask_process, flask_process.stderr, "[FLASK_ERR] "))
    flask_stdout_thread.daemon = True
    flask_stderr_thread.daemon = True
    flask_stdout_thread.start()
    flask_stderr_thread.start()

    time.sleep(10)  # サーバーの起動を待つ

    # Cloudflareトンネルの起動
    print("🌐 Cloudflare トンネルを開始しています...")
    tunnel_process = subprocess.Popen(['cloudflared', 'tunnel', '--url', 'http://localhost:5000'],
                                     stdout=subprocess.PIPE,
                                     stderr=subprocess.PIPE,
                                     text=True,
                                     bufsize=1)

    # Cloudflare Tunnelプロセスの出力を読み取るスレッドは削除
    tunnel_stdout_thread = threading.Thread(target=read_process_output, args=(tunnel_process, tunnel_process.stdout, "[CF_OUT] "))
    tunnel_stderr_thread = threading.Thread(target=read_process_output, args=(tunnel_process, tunnel_process.stderr, "[CF_ERR] "))
    tunnel_stdout_thread.daemon = True
    tunnel_stderr_thread.daemon = True
    tunnel_stdout_thread.start()
    tunnel_stderr_thread.start()


    # cloudflaredの出力からURLを抽出するループは維持
    url_found = False
    url = ""
    start_time = time.time()
    timeout = 130

    while time.time() - start_time < timeout:
        line = tunnel_process.stderr.readline() # Cloudflare TunnelはstderrにURLを出す傾向がある
        if line:
            # print(f"Cloudflare Tunnel stderr: {line.strip()}") # デバッグ出力は削除
            if 'https://' in line and 'trycloudflare.com' in line:
                match = re.search(r'(https:\/\/[^\s]+\.trycloudflare\.com)', line)
                if match:
                    url = match.group(0).strip()
                    url_found = True
                    break

        if tunnel_process.poll() is not None:
            print("Cloudflare Tunnelプロセスが予期せず終了しました。")
            break

        time.sleep(0.1)

    if url_found:
        print(f"✅ Cloudflare トンネルが開始されました: {url}")
        display(HTML(f'<a href="{url}" target="_blank" style="font-size:18px; color:pink;">アクセス: {url}</a>'))
    else:
        print("⚠️ CloudflareトンネルURLの取得に失敗しました。")
        # Cloudflare Tunnelプロセスの標準出力と標準エラー出力の表示は削除
        # print("Cloudflare Tunnelプロセスの標準出力と標準エラー出力を確認してください。")
        # final_stdout = tunnel_process.stdout.read()
        # final_stderr = tunnel_process.stderr.read()
        # if final_stdout:
        #     print(f"最終的なCloudflare Tunnel stdout: \n{final_stdout.strip()}")
        # if final_stderr:
        #     print(f"最終的なCloudflare Tunnel stderr: \n{final_stderr.strip()}")

        # スレッドのjoinも不要
        # tunnel_stdout_thread.join(timeout=5)
        # tunnel_stderr_thread.join(timeout=5)


    return flask_process, tunnel_process

def wait_for_flask_server(port=5000, timeout=15):
    """flaskサーバーが起動し、リクエストに応答するのを待機します。"""
    url = f"http://localhost:{port}"
    print(f"Waiting for Go server to start at {url}...")
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            response = requests.get(url, timeout=1)
            if response.status_code == 200:
                print(f"✅ flask server is up and running! Status code: {response.status_code}")
                return True
        except requests.exceptions.ConnectionError:
            pass # サーバーがまだ起動していない、または接続を拒否している
        except Exception as e:
            print(f"Error during flask server health check: {e}")
            pass
        time.sleep(1)
    print(f"❌ flask server did not respond within {timeout} seconds.")
    return False


def get_colab_external_ip():
    """Colabの外部IPアドレスを取得します。"""
    try:
        result = subprocess.run(['curl', 'ipinfo.io/ip'], capture_output=True, text=True, check=True)
        return result.stdout.strip()
    except Exception as e:
        print(f"⚠️ 外部IPアドレスの取得に失敗しました: {e}")
        return "UNKNOWN_IP"

selected_tunnel_service = ""
while True:
    print("\n--- トンネル方法を選択してください ---")
    print("1. Bore")
    print("2. Cloudflared")
    #print("3. Localtunnel (Node.js/npm が必要です)")
    choice = input("選択 (1/2): ").strip()

    if choice == '1':
        selected_tunnel_service = "bore"
        break
    elif choice == '2':
        selected_tunnel_service = "cloudflared"
        break
    else:
        print("無効な選択です。1 または 2 を入力してください。")


if selected_tunnel_service == "bore":
    flask_process, bore_process = setup_bore_tunnel()
    # bore_process.wait() # waitは削除
elif selected_tunnel_service == "cloudflared":
    flask_process, cloudflared_process = setup_cloudflare_tunnel()
    # tunnel_process.wait() # waitは削除

# プロセスがバックグラウンドで実行され続けるように、メインスレッドは特に待機しない
# Colabのセルが実行中である限り、子プロセスは実行を続けます。
# セルの実行が完了すると、これらのプロセスも通常終了します。

print(f"\nColab 外部IPアドレス: {get_colab_external_ip()}")
