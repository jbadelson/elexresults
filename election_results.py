#!env/bin/python

import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
import time
import yaml
from slack import WebClient

def get_root(url):
    r = requests.get(url)
    root = ET.fromstring(r.content)
    return root

def check_version(sos_api, update_time_url, sos_election_date, sos_access_key, sos_secret_key):
    url = f"{sos_api}/{update_time_url}/{sos_election_date}/{sos_access_key}/{sos_secret_key}"
    root = get_root(url)
    update_time = root.text

    return update_time

def get_races_candidates():
    sos_url = f"{sos_api}/{racecandidate_url}/{sos_election_date}/{sos_access_key}/{sos_secret_key}"
    r = requests.get(sos_url)
    root = ET.fromstring(r.content)
    races = {}
    for race in config['races']:
        races[race] = {'ID' : '', 'Users' : []}
        for user in config['users']:
            if config['races'][race] in config['users'][user]['races']:
                races[race]['Users'].append(config['users'][user]['userid'])
    candidates = {}
    for race in root.findall('Race'):
        race_fullname = race.attrib['ParishName']+' -- '+race.attrib['Title']
        if race_fullname in races.keys():
            races[race_fullname]['ID'] = race.attrib['ID']
            for candidate in race.findall('Choice'):
                candidates[candidate.attrib['ID']] = f"{candidate.attrib['Description']} ({candidate.attrib['Party']})"
    return races, candidates

def get_results(races):
    results = {}
    url = f"{sos_api}/{precinct_url}/{sos_election_date}/{sos_access_key}/{sos_secret_key}"
    root = get_root(url)
    for race in races.keys():
        results[race] = {'Votes' : {}, 'Status' : {'Early' : {'Total' : 0, 'Counted' : 0}, 'In-Person' : {'Total' : 0, 'Counted' : 0}, 'Updated' : False, 'Finished' : False}}
        elec = root.findall(f"""Race[@ID="{races[race]['ID']}"]""")
        total_precincts = 0
        total_earlyvote = 0
        counted_precincts = 0
        counted_earlyvote = 0

        for e in elec:
            counted = False
            parishwardprecinct = e.attrib['Parish']+e.attrib['Ward']+e.attrib['Precinct']
            precinct_votes = 0
            if 'Early' in parishwardprecinct:
                total_earlyvote += 1
            else:
                total_precincts += 1
            # parish = e.attrib['Parish']
            # test_race[parish] = {'precincts_reporting' : int(e.attrib['NumPrecinctsReporting']),
            #                     'precincts_total' : int(e.attrib['NumPrecinctsExpected'])}
            results[race]['Votes'][parishwardprecinct] = {}
            if 'Statewide' in results[race]['Votes'].keys():
                pass
            else:
                results[race]['Votes']['Statewide'] = {'Total' : 0}
            for c in e.findall('Choice'):
                candidate = c.attrib['ID']
                candidate_votes = None if c.attrib['VoteTotal'] == '' else float(c.attrib['VoteTotal'])
                results[race]['Votes'][parishwardprecinct][candidate] = candidate_votes
                if candidate_votes != None:
                    if candidate in results[race]['Votes']['Statewide'].keys():
                        results[race]['Votes']['Statewide'][candidate] += candidate_votes
                        precinct_votes += candidate_votes
                    else:
                        results[race]['Votes']['Statewide'][candidate] = candidate_votes
                        precinct_votes += candidate_votes
                    results[race]['Votes']['Statewide']['Total'] += candidate_votes
                    counted = True
                # else: 
                #     results[race]['Votes']['Statewide'][candidate] = 0
            if 'Early' in parishwardprecinct and counted == True:
                counted_earlyvote +=1
            elif counted == True:
                counted_precincts += 1
            else:
                pass
        if results[race]['Status']['Early']['Counted'] != counted_earlyvote or results[race]['Status']['In-Person']['Counted'] != counted_precincts:
            results[race]['Status']['Early']['Total'] = total_earlyvote
            results[race]['Status']['Early']['Counted'] = counted_earlyvote
            results[race]['Status']['In-Person']['Total'] = total_precincts
            results[race]['Status']['In-Person']['Counted'] = counted_precincts
            results[race]['Status']['Updated'] = True
            if counted_precincts != 0 and counted_earlyvote != 0 and counted_precincts == total_precincts and counted_earlyvote == total_earlyvote:
                results[race]['Status']['Finished'] = True
        else:
            results[race]['Status']['Updated'] = False
        #elif results[race]['Status']['Early']['Counted'] == counted_earlyvote and results[race['Status']['In-Person']['Counted'] == counted_earlyvote:
        #    results[race]['Status']['Updated'] = False
    return results
    
def send_update(results, candidates, races, stopped):
    client = WebClient('xoxb-65110774224-6040954929968-aDZbaNqNyAXOMSKdQiPE6y4Y')
    all_results = "This is a test of the Advocate elections app.\n"
    for race in results:
        if results[race]['Status']['Updated'] == True and race not in stopped:
            results_text = f" \n\n\n*{race.replace('Multi-Parish -- ', '').upper()}*\n\n"
            if results[race]['Status']['Finished'] == True:
                results_text += "*FINAL*\n"
            ip_counted = results[race]['Status']['In-Person']['Counted']
            ip_total = results[race]['Status']['In-Person']['Total']
            ev_counted = results[race]['Status']['Early']['Counted']
            ev_total = results[race]['Status']['Early']['Total']
            results_text += f"Precincts reporting: {ip_counted:,.0f}/{ip_total:,.0f} ({ip_counted/ip_total:.0%})\n"
            results_text += f"Parishes reporting early votes: {ev_counted:,.0f}/{ev_total:,.0f} ({ev_counted/ev_total:.0%})\n\n"
            candidate_count = 0
            runoff = True
            for candidate in sorted(results[race]['Votes']['Statewide'].items(), key=lambda candidate: candidate[1], reverse=True):
                if candidate[0] != 'Total':                   
                    candidate_count += 1 
                    if results[race]['Votes']['Statewide'][candidate[0]] > 0:
                        candidate_percent = results[race]['Votes']['Statewide'][candidate[0]]/results[race]['Votes']['Statewide']['Total']
                    else:
                        candidate_percent = 0
                    if results[race]['Status']['Finished'] != True:
                        results_text += f"*{candidates[candidate[0]]}*: {results[race]['Votes']['Statewide'][candidate[0]]:,.0f} ({candidate_percent:.1%})\n"
                    elif results[race]['Status']['Finished'] == True and candidate_percent > .5:
                        results_text += f"*WINNER: {candidates[candidate[0]]}*: {results[race]['Votes']['Statewide'][candidate[0]]:,.0f} ({candidate_percent:.1%})\n"
                        runoff = False
                    elif results[race]['Status']['Finished'] == True and candidate_percent <= .5 and runoff == False:
                        results_text += f"{candidates[candidate[0]]}: {results[race]['Votes']['Statewide'][candidate[0]]:,.0f} ({results[race]['Votes']['Statewide'][candidate[0]]/results[race]['Votes']['Statewide']['Total']:.1%})\n"
                    elif results[race]['Status']['Finished'] == True and candidate_percent < .5 and candidate_count <= 2 and runoff == True:
                        results_text += f"*RUN OFF: {candidates[candidate[0]]}*: {results[race]['Votes']['Statewide'][candidate[0]]:,.0f} ({results[race]['Votes']['Statewide'][candidate[0]]/results[race]['Votes']['Statewide']['Total']:.1%})\n"
                    elif results[race]['Status']['Finished'] == True and candidate_percent < .5 and candidate_count > 2:
                        results_text += f"{candidates[candidate[0]]}: {results[race]['Votes']['Statewide'][candidate[0]]:,.0f} ({results[race]['Votes']['Statewide'][candidate[0]]/results[race]['Votes']['Statewide']['Total']:.1%})\n"                        
            results_text += "\n\n\n "
            all_results += results_text
            for user in races[race]['Users']:
                response = client.conversations_open(users=user)
                client.chat_postMessage(channel=response['channel']['id'], text=results_text)
                time.sleep(1.5)
            if results[race]['Status']['Finished'] == True:
                stopped.append(race)

def main():
    print(f"[{datetime.now().strftime('%m/%d/%Y %H:%M:%S')}] Starting Advocate Elections App.")
    races, candidates = get_races_candidates()
    print(f"[{datetime.now().strftime('%m/%d/%Y %H:%M:%S')}] Races and candidates retrieved.")

    status = ''
    stopped = []
    no_result_time = "1/1/1900 12:00:00 AM"
    complete_time = "01/01/9999 12:00:00 AM"
    certified_time = "12/31/9999 12:59:59 PM"
    last_update = '1/1/2023'
    while status != 'finished':
        start_time = datetime.now()
        next_update_time = start_time+timedelta(minutes=1)
        update_time = check_version(sos_api, update_time_url, sos_election_date, sos_access_key, sos_secret_key)
        if update_time == no_result_time:
            current_time = datetime.now().strftime('%m/%d/%Y %H:%M:%S')
            print(f'[{current_time}] No results yet. Polling again in 60 seconds.')
        elif update_time == complete_time:
            results = get_results(races)
            send_update(results, candidates, races, stopped)
            current_time = datetime.now().strftime('%m/%d/%Y %H:%M:%S')
            print(f'[{current_time}] All results counted. Polling stopped.')
            status = 'finished'
        elif update_time == certified_time:
            current_time = datetime.now().strftime('%m/%d/%Y %H:%M:%S')
            print(f'[{current_time}] All results certified.')
            results = get_results(races)
            send_update(results, candidates, races, stopped)
            status = 'finished'
        elif update_time == last_update:
            current_time = datetime.now().strftime('%m/%d/%Y %H:%M:%S')
            print(f'[{current_time}] No new results. Most recent results are from {last_update}. Polling again in 60 seconds.')
        else:
            current_time = datetime.now().strftime('%m/%d/%Y %H:%M:%S')
            print(f"[{current_time}] Last update at {update_time}. Most recent results are from {last_update}. Getting new results.")
            results = get_results(races)
            current_time = datetime.now().strftime('%m/%d/%Y %H:%M:%S')
            print(f'[{current_time}] Sending new results.')
            send_update(results, candidates, races, stopped)
            current_time = datetime.now().strftime('%m/%d/%Y %H:%M:%S')
            print(f"[{current_time}] Results sent.")
        last_update = update_time
        next_update_seconds = (next_update_time-datetime.now()).total_seconds()
        delay = next_update_seconds if next_update_seconds>0 else 5
        time.sleep(delay)
    print(f"[{datetime.now().strftime('%m/%d/%Y %H:%M:%S')}] Election completed. App stopped.")

if __name__ == "__main__":

    with open("election_results.yaml", mode="r") as f:
        config = yaml.safe_load(f)

    sos_api = config['sos_api']
    sos_election_date = config['sos_election_date']
    # sos_election_date = '2023-10-14'
    sos_access_key = config['sos_access_key']
    sos_secret_key = config['sos_secret_key']
    slack_token = config['slack_token']

    precinct_url = 'PrecinctVotes'
    parish_url = 'ParishVotes'
    racecandidate_url = 'RacesAndCandidates'
    update_time_url = 'LatestVersion'

    main()
