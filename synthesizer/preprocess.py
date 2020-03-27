from multiprocessing.pool import Pool
from synthesizer.utils import audio
from functools import partial
from itertools import chain
from encoder import inference as encoder
from pathlib import Path
from utils import logmmse
from tqdm import tqdm
import numpy as np
import librosa


def preprocess_librispeech(datasets_root: Path, out_dir: Path, n_processes: int,
                           skip_existing: bool, hparams):
    # Gather the input directories
    dataset_root = datasets_root.joinpath("wavs")
    input_dirs = [dataset_root]
    print("\n    ".join(map(str, ["Using data from:"] + input_dirs)))
    assert all(input_dir.exists() for input_dir in input_dirs)

    # Create the output directories for each output file type
    out_dir.joinpath("mels").mkdir(exist_ok=True)
    out_dir.joinpath("audio").mkdir(exist_ok=True)

    # Create a metadata file
    metadata_fpath = out_dir.joinpath("train.txt")
    metadata_file = metadata_fpath.open("a" if skip_existing else "w", encoding="utf-8")

    # Preprocess the dataset
    speaker_dirs = list(chain.from_iterable(input_dir.glob("*") for input_dir in input_dirs))
    func = partial(preprocess_speaker, out_dir=out_dir, skip_existing=skip_existing,
                   hparams=hparams)
    job = Pool(n_processes).imap(func, speaker_dirs)
    for speaker_metadata in tqdm(job, dataset_root.stem, len(speaker_dirs), unit="speakers"):
        for metadatum in speaker_metadata:
            metadata_file.write("|".join(str(x) for x in metadatum) + "\n")
    metadata_file.close()

    # Verify the contents of the metadata file
    with metadata_fpath.open("r", encoding="utf-8") as metadata_file:
        metadata = [line.split("|") for line in metadata_file]
    mel_frames = sum([int(m[4]) for m in metadata])
    timesteps = sum([int(m[3]) for m in metadata])
    sample_rate = hparams.sample_rate
    hours = (timesteps / sample_rate) / 3600
    print("The dataset consists of %d utterances, %d mel frames, %d audio timesteps (%.2f hours)." %
          (len(metadata), mel_frames, timesteps, hours))
    print("Max input length (text chars): %d" % max(len(m[5]) for m in metadata))
    print("Max mel frames length: %d" % max(int(m[4]) for m in metadata))
    print("Max audio timesteps length: %d" % max(int(m[3]) for m in metadata))


def preprocess_user(datasets_root: Path, out_dir: Path, n_processes: int,
                    skip_existing: bool, hparams, datasets=None):
    """
    目录格式样例：
    datasets_root: E:\data\biaobei
    子目录为：biaobei

    音频目录为：biaobei/wavs
    音频文件为：000001.wav

    文本路径为：biaobei/metadata.csv
    文本样式为：000001	卡尔普陪外孙玩滑梯。

    :param datasets_root:
    :param out_dir:
    :param n_processes:
    :param skip_existing:
    :param hparams:
    :return:
    """
    # Gather the input directories
    if datasets is None:
        input_dirs = [datasets_root]
    else:
        input_dirs = [datasets_root.joinpath(w) for w in datasets.split()]
    print("\n    ".join(map(str, ["Using data from:"] + input_dirs)))
    assert all(input_dir.exists() for input_dir in input_dirs)

    # Create the output directories for each output file type
    out_dir.joinpath("mels").mkdir(exist_ok=True)
    out_dir.joinpath("audio").mkdir(exist_ok=True)

    for onedir in input_dirs:
        preprocess_speaker_user(onedir, out_dir=out_dir, skip_existing=skip_existing, hparams=hparams,
                                n_processes=n_processes)

    metadata_fpath = out_dir.joinpath("train.txt")
    # Verify the contents of the metadata file
    with metadata_fpath.open("r", encoding="utf-8") as metadata_file:
        metadata = [line.split("|") for line in metadata_file]
    mel_frames = sum([int(m[4]) for m in metadata])
    timesteps = sum([int(m[3]) for m in metadata])
    sample_rate = hparams.sample_rate
    hours = (timesteps / sample_rate) / 3600
    print("The dataset consists of %d utterances, %d mel frames, %d audio timesteps (%.2f hours)." %
          (len(metadata), mel_frames, timesteps, hours))
    print("Max input length (text chars): %d" % max(len(m[5]) for m in metadata))
    print("Max mel frames length: %d" % max(int(m[4]) for m in metadata))
    print("Max audio timesteps length: %d" % max(int(m[3]) for m in metadata))


def preprocess_speaker_user(speaker_dir, out_dir: Path, skip_existing: bool, hparams, n_processes=None):
    alignments_fpath = speaker_dir.joinpath('metadata.csv')
    with alignments_fpath.open("r", encoding='utf8') as alignments_file:
        alignments = [line.rstrip().split('\t') for line in alignments_file]

    # Create a metadata file
    metadata_fpath = out_dir.joinpath("train.txt")
    metadata_file = metadata_fpath.open("a" if skip_existing else "w", encoding="utf-8")

    if n_processes == 0:
        for line in tqdm(alignments, speaker_dir.stem, unit="it"):
            one_metadata = preprocess_utterance_user(
                line, speaker_dir=speaker_dir, out_dir=out_dir, skip_existing=skip_existing, hparams=hparams)
            if one_metadata:
                metadata_file.write("|".join(str(x) for x in one_metadata) + "\n")
    else:
        func = partial(preprocess_utterance_user, speaker_dir=speaker_dir, out_dir=out_dir, skip_existing=skip_existing,
                       hparams=hparams)
        job = Pool(n_processes).imap(func, alignments)

        for one_metadata in tqdm(job, speaker_dir.stem, len(alignments), unit="it"):
            if one_metadata:
                metadata_file.write("|".join(str(x) for x in one_metadata) + "\n")

    metadata_file.close()


def preprocess_utterance_user(line, speaker_dir, out_dir: Path, skip_existing: bool, hparams):
    fname, text = line
    wav_fpath = speaker_dir.joinpath('wavs', fname + ".wav")
    try:
        assert wav_fpath.exists()
        fname = fname.replace('/', '-')
        one_metadata = process_utterance(wav_fpath, text, out_dir, fname, skip_existing, hparams)
    except Exception as e:
        print(line)
        print(e)
        return None
    return one_metadata


def preprocess_speaker(speaker_dir, out_dir: Path, skip_existing: bool, hparams):
    metadata = []
    for book_dir in speaker_dir.glob("*"):
        # Gather the utterance audios and texts
        try:
            alignments_fpath = next(book_dir.glob("*.trans.txt"))
            with alignments_fpath.open("r") as alignments_file:
                alignments = [line.rstrip().split() for line in alignments_file]
        except StopIteration:
            # A few alignment files will be missing
            continue

        # Iterate over each entry in the alignments file
        for line in tqdm(alignments):
            wav_fname, words = line[0], line[1:]
            wav_fpath = book_dir.joinpath(wav_fname + ".wav")
            assert wav_fpath.exists()
            # words = words.replace("\"", "").split(",")
            # end_times = list(map(float, end_times.replace("\"", "").split(",")))
            end_times = None
            # Process each sub-utterance
            wavs, texts = split_on_silences(wav_fpath, words, end_times, hparams)
            for i, (wav, text) in enumerate(zip(wavs, texts)):
                sub_basename = "%s_%02d" % (wav_fname, i)
                metadata.append(process_utterance(wav, text, out_dir, sub_basename,
                                                  skip_existing, hparams))

    return [m for m in metadata if m is not None]


def split_on_silences(wav_fpath, words, end_times, hparams):
    # Load the audio waveform
    wav, _ = librosa.load(wav_fpath, hparams.sample_rate)
    if hparams.rescale:
        wav = wav / np.abs(wav).max() * hparams.rescaling_max

    text = ''.join(words)
    return [wav], [text]
    words = np.array(words)
    start_times = np.array([0.0] + end_times[:-1])
    end_times = np.array(end_times)
    assert len(words) == len(end_times) == len(start_times)
    assert words[0] == "" and words[-1] == ""

    # Find pauses that are too long
    mask = (words == "") & (end_times - start_times >= hparams.silence_min_duration_split)
    mask[0] = mask[-1] = True
    breaks = np.where(mask)[0]

    # Profile the noise from the silences and perform noise reduction on the waveform
    silence_times = [[start_times[i], end_times[i]] for i in breaks]
    silence_times = (np.array(silence_times) * hparams.sample_rate).astype(np.int)
    noisy_wav = np.concatenate([wav[stime[0]:stime[1]] for stime in silence_times])
    if len(noisy_wav) > hparams.sample_rate * 0.02:
        profile = logmmse.profile_noise(noisy_wav, hparams.sample_rate)
        wav = logmmse.denoise(wav, profile, eta=0)

    # Re-attach segments that are too short
    segments = list(zip(breaks[:-1], breaks[1:]))
    segment_durations = [start_times[end] - end_times[start] for start, end in segments]
    i = 0
    while i < len(segments) and len(segments) > 1:
        if segment_durations[i] < hparams.utterance_min_duration:
            # See if the segment can be re-attached with the right or the left segment
            left_duration = float("inf") if i == 0 else segment_durations[i - 1]
            right_duration = float("inf") if i == len(segments) - 1 else segment_durations[i + 1]
            joined_duration = segment_durations[i] + min(left_duration, right_duration)

            # Do not re-attach if it causes the joined utterance to be too long
            if joined_duration > hparams.hop_size * hparams.max_mel_frames / hparams.sample_rate:
                i += 1
                continue

            # Re-attach the segment with the neighbour of shortest duration
            j = i - 1 if left_duration <= right_duration else i
            segments[j] = (segments[j][0], segments[j + 1][1])
            segment_durations[j] = joined_duration
            del segments[j + 1], segment_durations[j + 1]
        else:
            i += 1

    # Split the utterance
    segment_times = [[end_times[start], start_times[end]] for start, end in segments]
    segment_times = (np.array(segment_times) * hparams.sample_rate).astype(np.int)
    wavs = [wav[segment_time[0]:segment_time[1]] for segment_time in segment_times]
    texts = [" ".join(words[start + 1:end]).replace("  ", " ") for start, end in segments]
    return wavs, texts


def process_utterance(wav_fpath: np.ndarray, text: str, out_dir: Path, basename: str,
                      skip_existing: bool, hparams):
    ## FOR REFERENCE:
    # For you not to lose your head if you ever wish to change things here or implement your own
    # synthesizer.
    # - Both the audios and the mel spectrograms are saved as numpy arrays
    # - There is no processing done to the audios that will be saved to disk beyond volume  
    #   normalization (in split_on_silences)
    # - However, pre-emphasis is applied to the audios before computing the mel spectrogram. This
    #   is why we re-apply it on the audio on the side of the vocoder.
    # - Librosa pads the waveform before computing the mel spectrogram. Here, the waveform is saved
    #   without extra padding. This means that you won't have an exact relation between the length
    #   of the wav and of the mel spectrogram. See the vocoder data loader.

    # Skip existing utterances if needed
    mel_fpath = out_dir.joinpath("mels", "mel-%s.npy" % basename)
    # wav_fpath = out_dir.joinpath("audio", "audio-%s.npy" % basename)
    if skip_existing and mel_fpath.exists():  # and wav_fpath.exists():
        return None

    wav, _ = librosa.load(wav_fpath, hparams.sample_rate)
    if hparams.rescale:
        wav = wav / np.abs(wav).max() * hparams.rescaling_max

    # Skip utterances that are too short
    if len(wav) < hparams.utterance_min_duration * hparams.sample_rate:
        return None

    # Compute the mel spectrogram
    mel_spectrogram = audio.melspectrogram(wav, hparams).astype(np.float32)
    mel_frames = mel_spectrogram.shape[1]

    # Skip utterances that are too long
    if mel_frames > hparams.max_mel_frames and hparams.clip_mels_length:
        return None

    # Write the spectrogram, embed and audio to disk
    np.save(mel_fpath, mel_spectrogram.T, allow_pickle=False)
    # np.save(wav_fpath, wav, allow_pickle=False)

    # Return a tuple describing this training example
    return str(wav_fpath).replace("\\", "/"), mel_fpath.name, "embed-%s.npy" % basename, len(wav), mel_frames, text


def embed_utterance(fpaths, encoder_model_fpath, hparams):
    if not encoder.is_loaded():
        encoder.load_model(encoder_model_fpath)

    # Compute the speaker embedding of the utterance
    wav_fpath, embed_fpath = fpaths
    if embed_fpath.exists():
        return
    # wav = np.load(wav_fpath)
    wav, _ = librosa.load(wav_fpath, hparams.sample_rate)
    if hparams.rescale:
        wav = wav / np.abs(wav).max() * hparams.rescaling_max

    wav = encoder.preprocess_wav(wav)
    embed = encoder.embed_utterance(wav)
    np.save(embed_fpath, embed, allow_pickle=False)


def create_embeddings(synthesizer_root: Path, encoder_model_fpath: Path, n_processes: int, hparams):
    wav_dir = synthesizer_root.joinpath("audio")
    metadata_fpath = synthesizer_root.joinpath("train.txt")
    assert wav_dir.exists() and metadata_fpath.exists()
    embed_dir = synthesizer_root.joinpath("embeds")
    embed_dir.mkdir(exist_ok=True)

    # Gather the input wave filepath and the target output embed filepath
    with metadata_fpath.open("r", encoding="utf8") as metadata_file:
        metadata = [line.split("|") for line in metadata_file]
        fpaths = [(m[0], embed_dir.joinpath(m[2])) for m in metadata]

    # TODO: improve on the multiprocessing, it's terrible. Disk I/O is the bottleneck here.
    # Embed the utterances in separate threads
    if n_processes == 0:
        for fpath in tqdm(fpaths):
            embed_utterance(fpath, encoder_model_fpath=encoder_model_fpath, hparams=hparams)
    else:
        func = partial(embed_utterance, encoder_model_fpath=encoder_model_fpath, hparams=hparams)
        job = Pool(n_processes).imap(func, fpaths)
        list(tqdm(job, "Embedding", len(fpaths), unit="utterances"))
