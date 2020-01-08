import sys
import json
import logging
import time
import configparser
import urllib
import datetime
import os
import random
from collections import OrderedDict
import requests
import lxml.html as lh
from pathlib import Path
import arxiv
import helpers
from database import Database
from helpers import Api
from helpers import Downloader

class Articles:
    def run(self):
        self.initialize()

        for item in self.sites:
            self.doItem(item)
            self.onItemIndex += 1

        self.cleanUp()

    def doItem(self, item):
        for keyword in self.keywords:
            self.showStatus(item, keyword)
            
            if self.isDone(item, keyword):
                continue

            try:
                self.lookUpItem(item, keyword)
                self.markDone(item, keyword)
            except Exception as e:
                logging.error(f'Skipping. Something went wrong.')
                logging.error(e)

    def lookUpItem(self, site, keyword):
        siteName = helpers.getDomainName(site.get('url', ''))

        self.totalResults = 0
        
        articles = []

        if siteName == 'nih.gov':
            articles = self.nihSearch(site, keyword)
        elif siteName == 'arxiv.org':
            articles = self.arxivSearch(site, keyword)
        else:
            siteData = {}
            
            keywordWithPlusSigns = keyword.replace(' ', '+')
            
            if siteName == 'biorxiv.org':
                siteData = {
                    'url': f'https://www.biorxiv.org/search/{keywordWithPlusSigns}%20numresults%3A75%20sort%3Arelevance-rank',
                    'resultsXpath': "//a[@class = 'highwire-cite-linked-title']",
                    'totalResultsXpath': "//*[@id = 'search-summary-wrapper']",
                    'urlPrefix': 'https://www.biorxiv.org',
                    'afterFirstPageSuffix': '?page={}'
                }
            elif siteName == 'medrxiv.org':
                siteData = {
                    'url': f'https://www.medrxiv.org/search/{keywordWithPlusSigns}%20numresults%3A75%20sort%3Arelevance-rank',
                    'resultsXpath': "//a[@class = 'highwire-cite-linked-title']",
                    'totalResultsXpath': "//*[@id = 'search-summary-wrapper']",
                    'urlPrefix': 'https://www.medrxiv.org',
                    'afterFirstPageSuffix': '?page={}'
                }

            articles = self.genericSearch(site, keyword, siteData)

        i = 0
        
        for article in articles:
            logging.info(f'Downloading item {i + 1} of {len(articles)}')
            self.outputResult(site, keyword, article)

    def showStatus(self, item, keyword):
        url = item.get('url', '')

        logging.info(f'Site {self.onItemIndex + 1} of {len(self.sites)}: {url}. Keyword {self.onKeywordIndex + 1} of {len(self.keywords)}: {keyword}.')

    def shouldStopForThisKeyword(self, index, log=True):
        result = False
        
        if index >= self.options['maximumResultsPerKeyword']:
            maximum = self.options['maximumResultsPerKeyword']
            
            if log:
                logging.info(f'Stopping. Reached the maximum of {maximum} results for this keyword.')
            
            result = True

        return result

    def nihSearch(self, site, keyword):
        results = []

        api = Api('http://eutils.ncbi.nlm.nih.gov')

        for i in range(0, 1000):
            pageResults = self.getNihPage(site, keyword, api, i, results, len(results))

            if not pageResults:
                logging.debug('Reached end of search results')
                break

            results += pageResults

            # have enough results?
            if self.shouldStopForThisKeyword(len(results)):
                break

            i += 1
        
        return results

    def getGenericSearchPage(self, site, keyword, siteData, pageIndex, existingResults, resultCount):
        results = []
        ids = []

        logging.info(f'Getting page {pageIndex + 1}')

        suffix = ''

        if pageIndex > 0:
            suffix = siteData.get('afterFirstPageSuffix', '')
            suffix = suffix.format(pageIndex)

        page = self.downloader.get(siteData['url'] + suffix)

        elements = self.downloader.getXpath(page, siteData['resultsXpath'])
        
        total = self.downloader.getXpath(page, siteData['totalResultsXpath'], True)
        total = helpers.numbersOnly(total)

        if not self.totalResults and total:
            self.totalResults = int(total)

            # log the search now because the download might fail
            self.logToCsvFiles(site, keyword, '', True, False)

        urls = []
        i = resultCount
        
        # get information about each item
        for element in elements:
            if self.shouldStopForThisKeyword(i, False):
                break

            i += 1
           
            url = element.attrib['href']
            url = siteData['urlPrefix'] + url

            # avoids duplicates
            if url in urls:
                continue

            urls.append(url)

            logging.info(f'Results: {len(urls)}. Url: {url}.')

            pdfUrl = url + '.full.pdf'
                
            articleId = self.getLastAfterSplit(url, '/')

            # this allows us to know when we reached the final page
            if self.isInArticleList(existingResults, articleId):
                continue

            result = [articleId, pdfUrl]
            
            results.append(result)

        return results

    def isInArticleList(self, articleList, articleId):
        result = False

        for article in articleList:
            if len(article) >= 2 and article[0] == articleId:
                result = True
                break

        return result

    def getNihPage(self, site, keyword, api, pageIndex, existingResults, resultCount):
        results = []

        logging.info(f'Getting page {pageIndex + 1}')

        resultsPerPage = 1000
        start = pageIndex * resultsPerPage

        response = api.get(f'/entrez/eutils/esearch.fcgi?db=pubmed&retmode=json&retstart={start}&retmax={resultsPerPage}&term={keyword}')

        if not self.totalResults:
            self.totalResults = response['esearchresult']['count']

            # log the search now because the download might fail
            self.logToCsvFiles(site, keyword, '', True, False)

        i = resultCount
        
        for item in response['esearchresult']['idlist']:
            if self.shouldStopForThisKeyword(i, False):
                break

            # avoid duplicates
            if self.isInArticleList(existingResults, item):
                continue

            i += 1
            
            summaryResponse = api.get(f'/entrez/eutils/esummary.fcgi?db=pubmed&id={item}&retmode=json')

            if 'result' in summaryResponse and item in summaryResponse['result']:
                articleSummary = summaryResponse['result'][item]
                
                title = articleSummary.get('title', '')[0:50]

                logging.info(f'Results: {i}. Id: {item}. Title: {title}...')

                # write these results to a separate csv
                self.logNihResultToCsvFile(site, keyword, articleSummary)

            pdfUrl = self.getPdfUrlFromSciHub(item)

            if not pdfUrl:
                continue
            
            result = [item, pdfUrl]
            
            results.append(result)

        return results

    def arxivSearch(self, site, keyword):
        results = []

        maximumResults = self.options['maximumResultsPerKeyword']

        if maximumResults == -1:
            maximumResults = None

        items = arxiv.query(query=keyword,
                    id_list=[],
                    max_results=maximumResults,
                    start = 0,
                    sort_by="relevance",
                    sort_order="descending",
                    prune=True,
                    iterative=False,
                    max_chunk_results=1000)

        ids = []

        for item in items:
            id = item.get('id', '')
            id = self.getLastAfterSplit(id, '/')

            # avoids duplicates
            if id in ids:
                continue

            ids.append(id)

            pdfUrl = item.get('pdf_url', '')

            if not pdfUrl:
                continue

            result = [id, pdfUrl]
            
            results.append(result)

            title = item.get('title', '')

            logging.info(f'Results: {len(results)}. Id: {id}. Title: {title}.')

        self.totalResults = len(results)

        # log the search now because the download might fail
        self.logToCsvFiles(site, keyword, '', True, False)

        return results

    def getLastAfterSplit(self, s, splitter):
        result = ''

        fields = s.split(splitter)

        if len(fields) > 0:
            result = fields[-1]

        return result

    def getArticleId(self, site, pdfUrl):
        return getLastAfterSplit(pdfUrl, '/')

    def genericSearch(self, site, keyword, siteData):
        results = []

        for i in range(0, 1000):
            pageResults = self.getGenericSearchPage(site, keyword, siteData, i, results, len(results))

            if not pageResults:
                logging.debug('Reached end of search results')
                break

            results += pageResults

            # have enough results?
            if self.shouldStopForThisKeyword(len(results)):
                break

            i += 1
        
        return results

    def outputResult(self, site, keyword, article):
        siteName = helpers.getDomainName(site.get('url', ''))

        if len(article) < 2:
            return

        articleId = article[0]
        pdfUrl = article[1]

        subdirectory2 = f'{siteName}_{self.dateStarted}'
        fileName = f'{articleId}.pdf'

        outputFileName = os.path.join(self.options['outputDirectory'], self.subdirectory, subdirectory2, fileName)

        helpers.makeDirectory(os.path.dirname(outputFileName))

        if self.existsInOutputDirectory(fileName):
            return

        self.downloader.downloadBinaryFile(pdfUrl, outputFileName)

        self.logToCsvFiles(site, keyword, outputFileName, False, True)

        self.waitBetween()

    def logToCsvFiles(self, site, keyword, outputFileName, searchLog, pdfLog):
        outputDirectory = os.path.join(self.options['outputDirectory'], self.subdirectory)
        
        now = datetime.datetime.now().strftime('%m%d%y-%H%M%S')
        
        dateUnderscore = self.dateStarted.replace('-', '_')

        searchLogFileName = f'output_searchlog_{dateUnderscore}.csv'
        pdfLogFileName = f'output_pdf_log_{self.dateStarted}.csv'
        
        searchLogFileName = os.path.join(outputDirectory, searchLogFileName)
        pdfLogFileName = os.path.join(outputDirectory, pdfLogFileName)

        helpers.makeDirectory(outputDirectory)
        
        if searchLog and not os.path.exists(searchLogFileName):
            helpers.toFile('Date-Time,Search terms,Websites,Number of papers', searchLogFileName)

        if pdfLog and not os.path.exists(pdfLogFileName):
            helpers.toFile('DateTime,SearchTerms,Website,FilenamePath', pdfLogFileName)
        
        siteName = site.get('name', '')

        searchLogLine = [now, keyword, siteName, self.totalResults]
        pdfLogLine = [now, keyword, siteName, outputFileName]

        if searchLog:
            self.appendCsvFile(searchLogLine, searchLogFileName)

        if pdfLog:
            self.appendCsvFile(pdfLogLine, pdfLogFileName)

    def logNihResultToCsvFile(self, site, keyword, article):
        outputDirectory = os.path.join(self.options['outputDirectory'], self.subdirectory)        

        name = site.get('name', '').lower()
        
        csvFileName = os.path.join(outputDirectory, f'{name}_results.csv')
        
        if not os.path.exists(csvFileName):
            helpers.toFile('Title,URL,Description,Details,ShortDetails,Resource,Type,Identifiers,Db,EntrezUID,Properties', csvFileName)

        siteName = site.get('name', '')

        articleId = article.get('uid', '')
        properties = 'create date: ' + helpers.findBetween(article.get('sortpubdate', ''), '', ' ') + ' | first author: ' + article.get('sortfirstauthor', '')
        description = ''

        authors = []
        for author in article.get('authors', ''):
            authors.append(author.get('name', ''))

        description = ', '.join(authors) + '.'

        publicationTypes = ', '.join(article.get('pubtype', []))

        details = article.get('fulljournalname', '') + '. ' + article.get('elocationid', '') + '. ' + publicationTypes + '.'
        
        line = [
            article.get('title', ''),
            f'/pubmed/{articleId}',
            description,
            details,
            article.get('fulljournalname', '') + '. ' + helpers.findBetween(article.get('sortpubdate', ''), '', '/'),
            'PubMed',
            publicationTypes,
            f'PMID:{articleId}',
            'pubmed',
            articleId,
            properties
        ]
        
        self.appendCsvFile(line, csvFileName)

    def appendCsvFile(self, line, fileName):
        import csv
        with open(fileName, "a", newline='\n', encoding='utf-8') as csv_file:
            writer = csv.writer(csv_file, delimiter=',')
            writer.writerow(line)

    def existsInOutputDirectory(self, fileName):
        result = False;

        if self.options['onlyOneCopyPerPdf'] != 1:
            return result
        
        for file in helpers.listFiles(self.options['outputDirectory'], False):
            if helpers.fileNameOnly(file, True) == fileName:
                outputDirectory = self.options['outputDirectory']
                logging.info(f'Skipping. Output file already exists in {outputDirectory}.')
                result = True
                break

        return result

    def getPdfUrlFromSciHub(self, articleId):
        result = ''

        api = Api('https://sci-hub.tw')

        body = {
            'sci-hub-plugin-check': '',
            'request': articleId
        }
        
        try:
            response = api.post('/', body, False)

            result = self.downloader.getXpath(response, "//*[@id = 'buttons']//a[contains(@onclick, '.pdf')]", True, 'onclick')

            result = result.replace("location.href='", 'https:')

            if result.endswith("'"):
                result = result[0:-1]
        except Exception as e:
            logging.error(e)

        if not result:
            logging.error(f'No result found on {api.urlPrefix} for {articleId}')

        return result

    def download(self, url, site, keyword):
        pass
    
    def isDone(self, site, keyword):
        result = False;

        siteName = helpers.getDomainName(site.get('url', ''))

        hours = self.options['minimumHoursBetweenRuns']

        minimumDate = helpers.getDateStringSecondsAgo(hours * 60 * 60, True)

        keyword = keyword.replace("'", "''")

        gmDateLastCompleted = self.database.getFirst('history', '*', f"siteName= '{siteName}' and keyword = '{keyword}' and gmDateLastCompleted >= '{minimumDate}'", '', '')

        if gmDateLastCompleted:
            logging.info(f'Skipping. Too soon since last completed this item.')
            result = True

        return result

    def markDone(self, site, keyword):
        siteName = helpers.getDomainName(site.get('url', ''))

        keyword = keyword.replace("'", "''")

        item = {
            'siteName': siteName,
            'keyword': keyword,
            'gmDateLastCompleted': str(datetime.datetime.utcnow())
        }

        logging.info(f'Inserting into database')
        logging.debug(item)
            
        self.database.insert('history', item)

    def waitBetween(self):
        secondsBetweenItems = self.options['secondsBetweenItems']

        if not secondsBetweenItems:
            return

        logging.info(f'Waiting {secondsBetweenItems} seconds')

        time.sleep(secondsBetweenItems)

    def cleanUp(self):
        self.database.close()

        logging.info('Done')

    def initialize(self):
        helpers.setUpLogging()

        logging.info('Starting\n')

        self.onItemIndex = 0
        self.onKeywordIndex = 0

        self.database = Database('database.sqlite')
        self.database.execute('create table if not exists history ( siteName text, keyword text, gmDateLastCompleted text, primary key(siteName, keyword) )')

        self.downloader = Downloader()
        self.dateStarted = datetime.datetime.now().strftime('%m%d%y-%H%M%S')
        self.subdirectory = f'WebSearch_{self.dateStarted}'

        outputDirectory = os.path.join(str(Path.home()), 'Desktop')

        self.options = {
            'inputWebsitesFile': 'input_websites.txt',
            'inputKeywordsFile': 'input_search_terms.txt',
            'outputDirectory': outputDirectory,
            'secondsBetweenItems': 1,
            'minimumHoursBetweenRuns': 12,
            'maximumDaysToKeepItems': 60,
            'maximumResultsPerKeyword': 25000,
            'onlyOneCopyPerPdf': 1
        }

        helpers.setOptions('options.ini', self.options)

        if '--debug' in sys.argv:
            self.options['secondsBetweenItems'] = 3
            self.options['maximumResultsPerKeyword'] = 2500

        self.options['inputWebsitesFile'] = helpers.getArgument('-w', True)
        self.options['inputKeywordsFile'] = helpers.getArgument('-s', True)

        file = helpers.getFile(self.options['inputWebsitesFile'])
        file = helpers.findBetween(file, "['", "']")
        sites = file.split("', '")
        self.sites = []

        for item in sites:
            name = helpers.findBetween(item, '', ':')
            url = helpers.findBetween(item, ':', '')

            site = {
                'name': name,
                'url': url
            }

            self.sites.append(site)

        keywordsFile = helpers.getFile(self.options['inputKeywordsFile'])
        list = keywordsFile.splitlines()
        self.keywords = []

        for line in list:
            self.keywords.append(helpers.findBetween(line, "'", "'"))

articles = Articles()
articles.run()