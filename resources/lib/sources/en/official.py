# -*- coding: utf-8 -*-

import re
import requests
from six.moves.urllib_parse import parse_qs, urlencode, quote_plus
from resources.lib.modules import api_keys
from resources.lib.modules import client
from resources.lib.modules import control
from resources.lib.modules import source_utils
from resources.lib.modules import log_utils
from resources.lib.modules.justwatch import JustWatch, providers


class source:
    def __init__(self):
        self.priority = 1
        self.country = control.setting('official.country') or 'US'
        self.tm_user = control.setting('tm.user') or api_keys.tmdb_key
        self.tmdb_by_imdb = 'https://api.themoviedb.org/3/find/%s?api_key=%s&external_source=imdb_id' % ('%s', self.tm_user)
        self.aliases = []


    def movie(self, imdb, tmdb, title, localtitle, aliases, year):
        if not providers.SCRAPER_INIT:
            return

        try:
            self.aliases.extend(aliases)
            url = {'imdb': imdb, 'tmdb': tmdb, 'title': title, 'year': year}
            url = urlencode(url)
            return url
        except:
            return


    def tvshow(self, imdb, tmdb, tvshowtitle, localtvshowtitle, aliases, year):
        if not providers.SCRAPER_INIT:
            return

        try:
            self.aliases.extend(aliases)
            url = {'imdb': imdb, 'tmdb': tmdb, 'tvshowtitle': tvshowtitle, 'year': year}
            url = urlencode(url)
            return url
        except Exception:
            return


    def episode(self, url, imdb, tmdb, title, premiered, season, episode):
        try:
            if url is None: return
            url = parse_qs(url)
            url = dict([(i, url[i][0]) if url[i] else (i, '') for i in url])
            url['title'], url['premiered'], url['season'], url['episode'] = title, premiered, season, episode
            url = urlencode(url)
            return url
        except Exception:
            return


    def sources(self, url):
        sources = []
        # sources.append({'source': 'test_addon', 'quality': '1080p', 'url': 'plugin://addon_id', 'official': True})
        try:
            if url is None: return sources

            data = parse_qs(url)
            data = dict([(i, data[i][0]) if data[i] else (i, '') for i in data])
            title = data['tvshowtitle'] if 'tvshowtitle' in data else data['title']
            year = data['year']
            content = 'movies' if not 'tvshowtitle' in data else 'tvshows'

            result = None

            jw = JustWatch(country=self.country)
            # r0 = jw.get_providers()
            # log_utils.log('justwatch {0} providers: {1}'.format(self.country, repr(r0)))

            if content == 'movies':
                tmdb = data['tmdb']
                if not tmdb or tmdb == '0':
                    tmdb = requests.get(self.tmdb_by_imdb % data['imdb']).json()
                    tmdb = tmdb['movie_results'][0]['id']
                    tmdb = str(tmdb)

                r = jw.search_for_item(query=title.lower(), content_types=['movie'], release_year_from=int(year)-1, release_year_until=int(year)+1)
                items = r['items']

                for item in items:
                    tmdb_id = item['scoring']
                    tmdb_id = [t['value'] for t in tmdb_id if t['provider_type'] == 'tmdb:id']
                    if tmdb_id and str(tmdb_id[0]) == tmdb:
                        result = item
                        break

            else:
                jw0 = JustWatch(country='US')
                r = jw0.search_for_item(query=title.lower(), content_types=['show'], release_year_from=int(year)-1, release_year_until=int(year)+1)
                items = r['items']
                #log_utils.log('jw items: ' + repr(items))
                jw_id = [i['id'] for i in items if source_utils.is_match(' '.join((i['title'], str(i['original_release_year']))), title, year, self.aliases)]

                if jw_id:
                    r = jw.get_episodes(str(jw_id[0]))
                    item = r['items']
                    item = [i for i in item if i['season_number'] == int(data['season']) and i['episode_number'] == int(data['episode'])]
                    if item:
                        result = item[0]
                    else:
                        for p in range(2, 5):
                            r = jw.get_episodes(str(jw_id[0]), page=p)
                            item = r['items']
                            item = [i for i in item if i['season_number'] == int(data['season']) and i['episode_number'] == int(data['episode'])]
                            if item:
                                result = item[0]
                                break

            if not result:
                raise Exception('%s not found in jw database' % title)
            #log_utils.log('justwatch result: ' + repr(result))

            offers = result.get('offers')
            if not offers:
                raise Exception('%s not available in %s' % (title, self.country))
            #log_utils.log('justwatch offers: ' + repr(offers))

            streams = []

            if providers.NETFLIX_ENABLED:
                nfx = [o for o in offers if o['provider_id'] in [8, 175]]
                if nfx:
                    nfx_id = nfx[0]['urls']['standard_web']
                    nfx_id = nfx_id.rstrip('/').split('/')[-1]
                    if content == 'movies':
                        netflix_id = nfx_id
                    else: # justwatch returns show ids for nf - get episode ids from reelgood
                        #netflix_id = self.get_nf_ep_id(nfx_id, data['season'], data['episode'])
                        netflix_id = self.get_rg_ep_id(title, year, data['season'], data['episode'], nfx=True)
                    if netflix_id:
                        streams.append(('netflix', 'plugin://plugin.video.netflix/play_strm/%s/' % netflix_id))

            if providers.PRIME_ENABLED:
                prv = [o for o in offers if o['provider_id'] in [9, 119, 613, 582] and o['monetization_type'] in ['free', 'ads', 'flatrate']]
                if prv:
                    prime_id = prv[0]['urls']['standard_web']
                    prime_id = prime_id.rstrip('/').split('gti=')[1]
                    streams.append(('amazon prime', 'plugin://plugin.video.amazon-test/?asin=%s&mode=PlayVideo&name=None&adult=0&trailer=0&selbitrate=0' % prime_id))

            if providers.HBO_ENABLED:
                hbm = [o for o in offers if o['provider_id'] in [616, 384, 27, 425] and o['monetization_type'] in ['free', 'ads', 'flatrate']]
                if hbm:
                    hbo_id = hbm[0]['urls']['standard_web']
                    hbo_id = hbo_id.rstrip('/').split('/')[-1]
                    streams.append(('hbo max', 'plugin://slyguy.hbo.max/?_=play&slug=' + hbo_id))

            if providers.DISNEY_ENABLED:
                dnp = [o for o in offers if o['provider_id'] == 337 and o['monetization_type'] in ['free', 'ads', 'flatrate']]
                if dnp:
                    disney_id = dnp[0]['urls']['deeplink_web']
                    disney_id = disney_id.rstrip('/').split('/')[-1]
                    streams.append(('disney+', 'plugin://slyguy.disney.plus/?_=play&_play=1&content_id=' + disney_id))

            if providers.IPLAYER_ENABLED:
                bbc = [o for o in offers if o['provider_id'] == 38]
                if bbc:
                    iplayer_url = bbc[0]['urls']['standard_web']
                    if content == 'tvshows' and '/episodes/' in iplayer_url: # justwatch sometimes returns season url for bbciplayer - get episode url from bbc
                        iplayer_id = self.get_bbc_ep_url(iplayer_url, data['season'], data['episode'])
                    else:
                        iplayer_id = iplayer_url
                    if iplayer_id:
                        streams.append(('bbc iplayer', 'plugin://plugin.video.iplayerwww/?mode=202&name=null&url=%s&iconimage=null&description=null' % quote_plus(iplayer_id)))

            if providers.CURSTREAM_ENABLED:
                cts = [o for o in offers if o['provider_id'] == 190]
                if cts:
                    cts_id = cts[0]['urls']['standard_web']
                    cts_id = cts_id.rstrip('/').split('/')[-1]
                    if control.condVisibility('System.HasAddon(slyguy.curiositystream)'):
                        uri = 'plugin://slyguy.curiositystream/?_=play&_play=1&id=' + cts_id
                    elif control.condVisibility('System.HasAddon(plugin.video.curiositystream)'):
                        uri = 'plugin://plugin.video.curiositystream/?action=play&media=' + cts_id
                    streams.append(('curiosity stream', uri))

            if providers.HULU_ENABLED:
                hlu = [o for o in offers if o['provider_id'] == 15]
                if hlu:
                    hulu_id = hlu[0]['urls']['standard_web']
                    hulu_id = hulu_id.rstrip('/').split('/')[-1]
                    streams.append(('hulu', 'plugin://slyguy.hulu/?_=play&id=' + hulu_id))

            if providers.PARAMOUNT_ENABLED:
                pmp = [o for o in offers if o['provider_id'] == 531]
                if pmp:
                    pmp_url = pmp[0]['urls']['standard_web']
                    pmp_id = pmp_url.split('?')[0].split('/')[-1] if content == 'movies' else re.findall('/video/(.+?)/', pmp_url)[0]
                    streams.append(('paramount+', 'plugin://slyguy.paramount.plus/?_=play&id=' + pmp_id))

            if providers.CRACKLE_ENABLED:
                crk = [o for o in offers if o['provider_id'] == 12]
                if crk:
                    if content == 'movies':
                        crk_id = crk[0]['urls']['standard_web']
                        crk_id = crk_id.rstrip('/').split('/')[-1]
                    else:
                        try:
                            crk_id = crk[0]['urls']['deeplink_android_tv']
                            crk_id = re.findall('intent://Media/(.+?)#', crk_id, flags=re.I)[0]
                        except:
                            crk_id = self.get_rg_ep_id(title, year, data['season'], data['episode'], crk=True)
                    if crk_id:
                        streams.append(('crackle', 'plugin://plugin.video.crackle/?id=%s&mode=103&type=%s' % (crk_id, content)))

            if providers.TUBI_ENABLED:
                tbv = [o for o in offers if o['provider_id'] == 73]
                if tbv:
                    tbv_url = tbv[0]['urls']['standard_web']
                    tbv_id = tbv_url.split('?')[0].strip('/').split('/')[-1]
                    if control.condVisibility('System.HasAddon(plugin.video.tubi.m7)'):
                        uri = 'plugin://plugin.video.tubi.m7/?mode=%splay-tubitv' % tbv_id
                    elif control.condVisibility('System.HasAddon(plugin.video.tubitv)'):
                        uri = 'plugin://plugin.video.tubitv/?mode=GV&url=' + tbv_id
                    streams.append(('tubi tv', uri))

            if providers.UKTVPLAY_ENABLED:
                ukt = [o for o in offers if o['provider_id'] == 137]
                if ukt:
                    ukt_url = ukt[0]['urls']['standard_web']
                    ukt_id = ukt_url.split('?')[0].strip('/').split('/')[-1]
                    streams.append(('uktv play', 'plugin://plugin.video.catchuptvandmore/resources/lib/channels/uk/uktvplay/get_video_url/?item_id=uktvplay&data_video_id=' + ukt_id))

            if providers.PLUTO_ENABLED:
                ptv = [o for o in offers if o['provider_id'] == 300]
                if ptv:
                    ptv_url = ptv[0]['urls']['deeplink_rokuos']
                    ptv_id = re.findall('contentID=(.+?)&', ptv_url)[0]
                    streams.append(('pluto tv', 'plugin://plugin.video.plutotv/play/vod/' + ptv_id))

            if providers.ITV_ENABLED:
                itv = [o for o in offers if o['provider_id'] == 41]
                if itv:
                    itv_url = itv[0]['urls']['standard_web']
                    streams.append(('itv hub', 'plugin://plugin.video.itvhub/resources/lib/main/play_title/?url=' + quote_plus(itv_url)))

            if streams:
                for s in streams:
                    sources.append({'source': s[0], 'quality': '1080p', 'url': s[1], 'official': True})

            return sources
        except:
            log_utils.log('Official scraper exc', 1)
            return sources


    def resolve(self, url):
        return url


    def get_bbc_ep_url(self, url, season, episode):
        try:
            import simplejson as json

            try: seriesId = url.split('seriesId=')[1]
            except: seriesId = None

            r = requests.get(url, timeout=10).text
            eps = re.findall('__IPLAYER_REDUX_STATE__\s*=\s*({.+?});</script>', r)[0]
            eps = json.loads(eps)

            if seriesId:
                seasons = eps['header']['availableSlices']
                series_id = [s['id'] for s in seasons if re.sub('[^0-9]', '', s['title']) == season][0]
                if not series_id == seriesId:
                    url = url.replace(seriesId, series_id)
                    r = requests.get(url, timeout=10).text
                    eps = re.findall('__IPLAYER_REDUX_STATE__\s*=\s*({.+?});</script>', r)[0]
                    eps = json.loads(eps)

            eps = eps['entities']
            eps = [e['props']['href'] for e in eps]
            ep = [e for e in eps if re.compile(r'series-%s-%s-' % (season, episode)).findall(e)][0]
            ep = 'https://www.bbc.co.uk' + ep if not ep.startswith('http') else ep
            return ep
        except:
            return


    def get_rg_ep_id(self, title, year, season, episode, nfx=False, crk=False):
        try:
            title = title.replace(' ', '-').lower()
            url = 'https://reelgood.com/show/' + '-'.join((title, year))
            r = client.request(url)
            #log_utils.log('r: ' + r)
            r = r.replace('\\u002F', '/')
            sequence = '%s.%04d' % (season, int(episode))
            sequence = sequence.rstrip('0')
            m = re.compile('"sequence_number":' + sequence + ',"aired_at":".+?","availability":\[(.+?)\]').findall(r)[0]
            ep_id = None
            if nfx:
                ep_id = re.compile('"source_name":"netflix","access_type":2,"source_data":\{"links":\{.+?\},"references":\{.*?"web":\{"episode_id":"(.+?)"').findall(m)[0]
            elif crk:
                ep_id = re.compile('"source_name":"crackle","access_type":0,"source_data":\{"links":\{.+?\},"references":\{.*?"web":\{"episode_id":"(.+?)"').findall(m)[0]

            return ep_id
        except:
            log_utils.log('get_crk_ep_id fail', 1)
            return


    # def get_nf_ep_id(self, show_id, season, episode):
        # # site has changed and doesn't provide episode ids anymore
        # try:
            # countryDict = {'AR': '21', 'AU': '23', 'BE': '26', 'BR': '29', 'CA': '33', 'CO': '36', 'CZ': '307', 'FR': '45', 'DE': '39', 'GR': '327', 'HK': '331', 'HU': '334',
                           # 'IS': '265', 'IN': '337', 'IL': '336', 'IT': '269', 'JP': '267', 'LT': '357', 'MY': '378', 'MX': '65', 'NL': '67', 'PL': '392', 'PT': '268', 'RU': '402',
                           # 'SG': '408', 'SK': '412', 'ZA': '447', 'KR': '348', 'ES': '270', 'SE': '73', 'CH': '34', 'TH': '425', 'TR': '432', 'GB': '46', 'US': '78'}

            # code = countryDict.get(self.country, '78')
            # url = 'https://www.instantwatcher.com/netflix/%s/title/%s' % (code, show_id)
            # r = requests.get(url, timeout=10).text
            # r = client.parseDOM(r, 'div', attrs={'class': 'tdChildren-titles'})[0]
            # seasons = re.findall(r'(<div class="iw-title netflix-title list-title".+?<div class="grandchildren-titles"></div></div>)', r, flags=re.I|re.S)
            # _season = [s for s in seasons if re.findall(r'>Season (.+?)</a>', s, flags=re.I|re.S)[0] == season][0]
            # episodes = client.parseDOM(_season, 'a', ret='data-title-id')
            # episode_id = episodes[int(episode)]

            # return episode_id
        # except:
            # log_utils.log('get_nf_ep_id fail', 1)
            # return


