import os

def shorten_filenames(directory, max_length=10):
    """
    指定ディレクトリ内のファイルを短い名前にリネームする
    :param directory: 処理対象のディレクトリ
    :param max_length: 新しいファイル名の最大長（拡張子を除く）
    """
    pref_counter = {}
    for filename in os.listdir(directory):
        filepath = os.path.join(directory, filename)
        if os.path.isfile(filepath):
            # 拡張子を分離
            name, ext = os.path.splitext(filename)

            if name[:max_length] in pref_counter:
                pref_counter[name[:max_length]] += 1
            else:
                pref_counter[name[:max_length]] = 0

            # 新しいファイル名（先頭から max_length 文字）
            new_name = f'{name[:max_length]}{pref_counter[name[:max_length]]:02x}{ext}'
            new_path = os.path.join(directory, new_name)

            # 同名ファイルが存在する場合は連番を付ける
            counter = 1
            while os.path.exists(new_path):
                new_name = f"{name[:max_length]}{counter:04}{ext}"
                new_path = os.path.join(directory, new_name)
                counter += 1

            # リネーム実行
            os.rename(filepath, new_path)
            print(f"Renamed: {filename} -> {new_name}")

if __name__ == "__main__":
    shorten_filenames("gtfs_data", max_length=2)
