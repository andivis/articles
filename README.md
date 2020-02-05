# articles

## Installation

1. Make sure Python 3.6 or higher, pip and git are installed. For example, on Ubuntu run the commands below in a terminal.

```
sudo apt install -y python3
sudo apt install -y python3-pip
sudo apt install -y git
```

2. Open a terminal window
3. Run the commands below. Depending on your system you may need run `pip` instead of `pip3`.

```
git clone https://github.com/andivis/articles.git
cd articles
pip install arxiv
pip install lxml
pip install wget
pip install xmltodict
```

## Instructions

1. Open a terminal window. Cd to the directory containing `articles.py`. It's where you cloned the repository before.
2. Optionally, edit the `options.ini` file to your liking
3. Edit `input_search_terms.txt` to contain your desired search terms. Each line is a search term.
4. Run `python articles.py -w input_websites.txt -s input_search_terms.txt -d ~/Desktop/WebSearch_010820`. The `-d` argument allows you to resume a partially completed run of this app.
5. Depending on your system you may need run `python3` instead of `python`.
6. To run multiple instances at the same time, run `bash run.sh`. That will run one instance for each site. That means it will finish four time faster.

## Command line parameters

- `-w`: file containing the list of websites. Default: `input_websites.txt`.
- `-s`: file containing the list of search terms. Default: the value in the `[search terms]` section in `options.ini`.
- `-d`: where to write the pdf files and logs. Default: `~/Desktop/WebSearch_(current date)`.
- `-i`: if this parameter is present, the script will download the article id's in the id list files specified in `options.ini`. It can be simply `-i`. Nothing needs to follow it. Default is off.

## Options

`options.ini` accepts the following options:

- `maximumResultsPerKeyword`: How many pdf's to download for a given site/keyword combination. -1 means no limit. Default 25000.
- `directoryToCheckForDuplicates`: Only download a pdf if it does not exist anywhere in this directory. Blank means don't check any directory. No quotes on directory name.

### Search terms section

```
[search terms]
(site name in lowercase)=(some file containing the search terms)
```

Example:

```
[search terms]
pubmed=input_search_terms_pubmed.txt
biorxiv=input_search_terms_biorxiv_medrxiv.txt
arxiv=input_search_terms_arxiv.txt
medrxiv=input_search_terms_biorxiv_medrxiv.txt
```

### ID lists section

```
[id lists]
(site name in lowercase)=(some file containing the article id's)
```

Example:

```
[id lists]
pubmed=id_list_pubmed.txt
biorxiv=id_list_biorxiv.txt
arxiv=id_list_arxiv.txt
medrxiv=id_list_medrxiv.txt
```