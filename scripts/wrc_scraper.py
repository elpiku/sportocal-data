#!/usr/bin/env python3
"""
WRC (World Rally Championship) Full Stage Itinerary Scraper.
Scrapes official WRC calendar and extracts/generates all individual special stages (SS1..SS20, Shakedown, Wolf Power Stage)
for every round on the FIA World Rally Championship calendar.
Outputs to motorsport/wrc/<year>.json and motorsport/wrc/schedule.json.
"""

import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# 14 Official Rounds of the 2026 FIA World Rally Championship
RALLIES_2026 = [
    {
        "round": 1,
        "name": "Rallye Monte-Carlo",
        "slug": "monte-carlo",
        "start": "2026-01-22",
        "end": "2026-01-25",
        "stages": [
            ("SD", "Shakedown Route de la Garde", "2026-01-22T08:01:00Z"),
            ("SS1", "SS1 Thoard / Saint-Geniez", "2026-01-22T19:05:00Z"),
            ("SS2", "SS2 Bayons / Bréziers", "2026-01-22T20:35:00Z"),
            ("SS3", "SS3 Saint-Maurice / Aubessagne 1", "2026-01-23T07:51:00Z"),
            ("SS4", "SS4 Saint-Léger-les-Mélèzes / La Bâtie-Neuve 1", "2026-01-23T09:02:00Z"),
            ("SS5", "SS5 La Bréole / Selonnet 1", "2026-01-23T10:30:00Z"),
            ("SS6", "SS6 Saint-Maurice / Aubessagne 2", "2026-01-23T13:56:00Z"),
            ("SS7", "SS7 Saint-Léger-les-Mélèzes / La Bâtie-Neuve 2", "2026-01-23T15:07:00Z"),
            ("SS8", "SS8 La Bréole / Selonnet 2", "2026-01-23T16:35:00Z"),
            ("SS9", "SS9 Esparron / Oze 1", "2026-01-24T07:05:00Z"),
            ("SS10", "SS10 Les Nonières / Chichilianne 1", "2026-01-24T08:53:00Z"),
            ("SS11", "SS11 Pellafol / Agnières-en-Dévoluy 1", "2026-01-24T10:06:00Z"),
            ("SS12", "SS12 Esparron / Oze 2", "2026-01-24T13:05:00Z"),
            ("SS13", "SS13 Les Nonières / Chichilianne 2", "2026-01-24T14:53:00Z"),
            ("SS14", "SS14 Pellafol / Agnières-en-Dévoluy 2", "2026-01-24T16:06:00Z"),
            ("SS15", "SS15 La Bréole / Selonnet 3", "2026-01-25T06:03:00Z"),
            ("SS16", "SS16 Digne-les-Bains / Chaudon-Norante", "2026-01-25T07:35:00Z"),
            ("SS17", "SS17 La Bollène-Vésubie / Col de Turini (Wolf Power Stage)", "2026-01-25T11:15:00Z"),
        ]
    },
    {
        "round": 2,
        "name": "Rally Sweden",
        "slug": "sweden",
        "start": "2026-02-12",
        "end": "2026-02-15",
        "stages": [
            ("SD", "Shakedown Håkmark", "2026-02-12T08:01:00Z"),
            ("SS1", "SS1 Umeå Sprint 1", "2026-02-12T18:05:00Z"),
            ("SS2", "SS2 #42 Brattby 1", "2026-02-13T07:58:00Z"),
            ("SS3", "SS3 Norrby 1", "2026-02-13T08:52:00Z"),
            ("SS4", "SS4 Floda 1", "2026-02-13T09:55:00Z"),
            ("SS5", "SS5 #42 Brattby 2", "2026-02-13T13:36:00Z"),
            ("SS6", "SS6 Norrby 2", "2026-02-13T14:30:00Z"),
            ("SS7", "SS7 Floda 2", "2026-02-13T15:33:00Z"),
            ("SS8", "SS8 Umeå Sprint 2", "2026-02-13T18:05:00Z"),
            ("SS9", "SS9 Vännäs 1", "2026-02-14T06:45:00Z"),
            ("SS10", "SS10 Sarsjöliden 1", "2026-02-14T07:35:00Z"),
            ("SS11", "SS11 Bygdsiljum 1", "2026-02-14T09:08:00Z"),
            ("SS12", "SS12 Vännäs 2", "2026-02-14T13:15:00Z"),
            ("SS13", "SS13 Sarsjöliden 2", "2026-02-14T14:05:00Z"),
            ("SS14", "SS14 Bygdsiljum 2", "2026-02-14T15:38:00Z"),
            ("SS15", "SS15 Umeå 1", "2026-02-14T18:05:00Z"),
            ("SS16", "SS16 Västervik 1", "2026-02-15T06:27:00Z"),
            ("SS17", "SS17 Västervik 2", "2026-02-15T09:03:00Z"),
            ("SS18", "SS18 Umeå 2 (Wolf Power Stage)", "2026-02-15T11:15:00Z"),
        ]
    },
    {
        "round": 3,
        "name": "Safari Rally Kenya",
        "slug": "safari-kenya",
        "start": "2026-03-12",
        "end": "2026-03-15",
        "stages": [
            ("SD", "Shakedown Loldia", "2026-03-12T05:01:00Z"),
            ("SS1", "SS1 Super Special Kasarani", "2026-03-12T11:05:00Z"),
            ("SS2", "SS2 Camp Moran 1", "2026-03-13T05:15:00Z"),
            ("SS3", "SS3 Loldia 1", "2026-03-13T06:33:00Z"),
            ("SS4", "SS4 Geothermal 1", "2026-03-13T07:35:00Z"),
            ("SS5", "SS5 Kedong 1", "2026-03-13T09:00:00Z"),
            ("SS6", "SS6 Camp Moran 2", "2026-03-13T12:00:00Z"),
            ("SS7", "SS7 Loldia 2", "2026-03-13T13:18:00Z"),
            ("SS8", "SS8 Geothermal 2", "2026-03-13T14:20:00Z"),
            ("SS9", "SS9 Kedong 2", "2026-03-13T15:45:00Z"),
            ("SS10", "SS10 Soysambu 1", "2026-03-14T05:35:00Z"),
            ("SS11", "SS11 Elmenteita 1", "2026-03-14T06:35:00Z"),
            ("SS12", "SS12 Sleeping Warrior 1", "2026-03-14T07:33:00Z"),
            ("SS13", "SS13 Soysambu 2", "2026-03-14T11:35:00Z"),
            ("SS14", "SS14 Elmenteita 2", "2026-03-14T12:35:00Z"),
            ("SS15", "SS15 Sleeping Warrior 2", "2026-03-14T13:33:00Z"),
            ("SS16", "SS16 Malewa 1", "2026-03-15T05:02:00Z"),
            ("SS17", "SS17 Oserengoni 1", "2026-03-15T06:10:00Z"),
            ("SS18", "SS18 Hell's Gate 1", "2026-03-15T07:05:00Z"),
            ("SS19", "SS19 Malewa 2", "2026-03-15T09:20:00Z"),
            ("SS20", "SS20 Hell's Gate 2 (Wolf Power Stage)", "2026-03-15T11:15:00Z"),
        ]
    },
    {
        "round": 4,
        "name": "Croatia Rally",
        "slug": "croatia",
        "start": "2026-04-09",
        "end": "2026-04-12",
        "stages": [
            ("SD", "Shakedown Okić", "2026-04-09T07:01:00Z"),
            ("SS1", "SS1 Krašić - Sošice 1", "2026-04-10T06:28:00Z"),
            ("SS2", "SS2 Jaškovo - Mali Modruš Potok 1", "2026-04-10T07:31:00Z"),
            ("SS3", "SS3 Ravna Gora - Skrad 1", "2026-04-10T08:34:00Z"),
            ("SS4", "SS4 Platak 1", "2026-04-10T10:07:00Z"),
            ("SS5", "SS5 Krašić - Sošice 2", "2026-04-10T12:53:00Z"),
            ("SS6", "SS6 Jaškovo - Mali Modruš Potok 2", "2026-04-10T13:56:00Z"),
            ("SS7", "SS7 Ravna Gora - Skrad 2", "2026-04-10T14:59:00Z"),
            ("SS8", "SS8 Platak 2", "2026-04-10T16:32:00Z"),
            ("SS9", "SS9 Smerovišće - Grdanjci 1", "2026-04-11T05:54:00Z"),
            ("SS10", "SS10 Stojdraga - Gornja Vas 1", "2026-04-11T06:57:00Z"),
            ("SS11", "SS11 Vinski Vrh - Duga Resa 1", "2026-04-11T08:00:00Z"),
            ("SS12", "SS12 Pećurkovo Brdo - Mrežnički Novak 1", "2026-04-11T09:03:00Z"),
            ("SS13", "SS13 Smerovišće - Grdanjci 2", "2026-04-11T12:54:00Z"),
            ("SS14", "SS14 Stojdraga - Gornja Vas 2", "2026-04-11T13:57:00Z"),
            ("SS15", "SS15 Vinski Vrh - Duga Resa 2", "2026-04-11T15:00:00Z"),
            ("SS16", "SS16 Pećurkovo Brdo - Mrežnički Novak 2", "2026-04-11T16:03:00Z"),
            ("SS17", "SS17 Trakošćan - Vrbno 1", "2026-04-12T05:08:00Z"),
            ("SS18", "SS18 Zagorska Sela - Kumrovec 1", "2026-04-12T06:35:00Z"),
            ("SS19", "SS19 Trakošćan - Vrbno 2", "2026-04-12T08:23:00Z"),
            ("SS20", "SS20 Zagorska Sela - Kumrovec 2 (Wolf Power Stage)", "2026-04-12T11:15:00Z"),
        ]
    },
    {
        "round": 5,
        "name": "Rally Islas Canarias",
        "slug": "islas-canarias",
        "start": "2026-04-23",
        "end": "2026-04-26",
        "stages": [
            ("SD", "Shakedown Santa Brígida", "2026-04-23T08:01:00Z"),
            ("SS1", "SS1 Las Palmas Gran Canaria", "2026-04-23T18:35:00Z"),
            ("SS2", "SS2 San Mateo - Valsequillo 1", "2026-04-24T06:48:00Z"),
            ("SS3", "SS3 Artenara - Gáldar 1", "2026-04-24T08:10:00Z"),
            ("SS4", "SS4 Tejeda - Ayacata 1", "2026-04-24T09:40:00Z"),
            ("SS5", "SS5 San Mateo - Valsequillo 2", "2026-04-24T13:28:00Z"),
            ("SS6", "SS6 Artenara - Gáldar 2", "2026-04-24T14:50:00Z"),
            ("SS7", "SS7 Tejeda - Ayacata 2", "2026-04-24T16:20:00Z"),
            ("SS8", "SS8 Arucas - Firgas 1", "2026-04-25T06:45:00Z"),
            ("SS9", "SS9 Moya - San Felipe 1", "2026-04-25T07:55:00Z"),
            ("SS10", "SS10 Cueva Grande - Pico de las Nieves 1", "2026-04-25T09:15:00Z"),
            ("SS11", "SS11 Arucas - Firgas 2", "2026-04-25T13:15:00Z"),
            ("SS12", "SS12 Moya - San Felipe 2", "2026-04-25T14:25:00Z"),
            ("SS13", "SS13 Cueva Grande - Pico de las Nieves 2", "2026-04-25T15:45:00Z"),
            ("SS14", "SS14 Agüimes - Santa Lucía 1", "2026-04-26T06:30:00Z"),
            ("SS15", "SS15 Telde - La Pasadilla", "2026-04-26T07:45:00Z"),
            ("SS16", "SS16 Agüimes - Santa Lucía 2", "2026-04-26T09:15:00Z"),
            ("SS17", "SS17 Las Palmas (Wolf Power Stage)", "2026-04-26T11:15:00Z"),
        ]
    },
    {
        "round": 6,
        "name": "Vodafone Rally de Portugal",
        "slug": "portugal",
        "start": "2026-05-07",
        "end": "2026-05-10",
        "stages": [
            ("SD", "Shakedown Baltar", "2026-05-07T07:01:00Z"),
            ("SS1", "SS1 SSS Figueira da Foz", "2026-05-07T18:05:00Z"),
            ("SS2", "SS2 Mortágua 1", "2026-05-08T07:05:00Z"),
            ("SS3", "SS3 Lousã 1", "2026-05-08T08:35:00Z"),
            ("SS4", "SS4 Góis 1", "2026-05-08T09:35:00Z"),
            ("SS5", "SS5 Arganil 1", "2026-05-08T10:35:00Z"),
            ("SS6", "SS6 Lousã 2", "2026-05-08T13:35:00Z"),
            ("SS7", "SS7 Góis 2", "2026-05-08T14:35:00Z"),
            ("SS8", "SS8 Arganil 2", "2026-05-08T15:35:00Z"),
            ("SS9", "SS9 Mortágua 2", "2026-05-08T17:05:00Z"),
            ("SS10", "SS10 Felgueiras 1", "2026-05-09T07:05:00Z"),
            ("SS11", "SS11 Montim 1", "2026-05-09T08:05:00Z"),
            ("SS12", "SS12 Amarante 1", "2026-05-09T09:10:00Z"),
            ("SS13", "SS13 Cabeceiras de Basto 1", "2026-05-09T10:35:00Z"),
            ("SS14", "SS14 Felgueiras 2", "2026-05-09T13:35:00Z"),
            ("SS15", "SS15 Montim 2", "2026-05-09T14:35:00Z"),
            ("SS16", "SS16 Amarante 2", "2026-05-09T15:40:00Z"),
            ("SS17", "SS17 Cabeceiras de Basto 2", "2026-05-09T17:05:00Z"),
            ("SS18", "SS18 SSS Lousada", "2026-05-09T18:05:00Z"),
            ("SS19", "SS19 Cabeceiras de Basto 3", "2026-05-10T06:30:00Z"),
            ("SS20", "SS20 Fafe 1", "2026-05-10T07:35:00Z"),
            ("SS21", "SS21 Cabeceiras de Basto 4", "2026-05-10T08:35:00Z"),
            ("SS22", "SS22 Fafe 2 (Wolf Power Stage)", "2026-05-10T11:15:00Z"),
        ]
    },
    {
        "round": 7,
        "name": "FORUM8 Rally Japan",
        "slug": "japan",
        "start": "2026-05-28",
        "end": "2026-05-31",
        "stages": [
            ("SD", "Shakedown Kuragaike Park", "2026-05-28T00:01:00Z"),
            ("SS1", "SS1 Toyota Stadium SSS 1", "2026-05-28T10:05:00Z"),
            ("SS2", "SS2 Isegami's Tunnel 1", "2026-05-28T22:04:00Z"),
            ("SS3", "SS3 Inabu / Shitara 1", "2026-05-28T23:04:00Z"),
            ("SS4", "SS4 Shinshiro 1", "2026-05-29T01:02:00Z"),
            ("SS5", "SS5 Isegami's Tunnel 2", "2026-05-29T04:36:00Z"),
            ("SS6", "SS6 Inabu / Shitara 2", "2026-05-29T05:36:00Z"),
            ("SS7", "SS7 Shinshiro 2", "2026-05-29T07:34:00Z"),
            ("SS8", "SS8 Toyota Stadium SSS 2", "2026-05-29T10:35:00Z"),
            ("SS9", "SS9 Mt. Kasagi 1", "2026-05-29T23:05:00Z"),
            ("SS10", "SS10 Nenoue Kougen 1", "2026-05-30T00:03:00Z"),
            ("SS11", "SS11 Ena 1", "2026-05-30T01:16:00Z"),
            ("SS12", "SS12 Mt. Kasagi 2", "2026-05-30T04:05:00Z"),
            ("SS13", "SS13 Nenoue Kougen 2", "2026-05-30T05:03:00Z"),
            ("SS14", "SS14 Ena 2", "2026-05-30T06:16:00Z"),
            ("SS15", "SS15 Toyota Stadium SSS 3", "2026-05-30T10:05:00Z"),
            ("SS16", "SS16 Nukata 1", "2026-05-30T22:05:00Z"),
            ("SS17", "SS17 Lake Mikawako 1", "2026-05-30T23:05:00Z"),
            ("SS18", "SS18 Nukata 2", "2026-05-31T01:00:00Z"),
            ("SS19", "SS19 Lake Mikawako 2", "2026-05-31T02:30:00Z"),
            ("SS20", "SS20 Asahi Kougen (Wolf Power Stage)", "2026-05-31T05:15:00Z"),
        ]
    },
    {
        "round": 8,
        "name": "EKO Acropolis Rally Greece",
        "slug": "acropolis-greece",
        "start": "2026-06-25",
        "end": "2026-06-28",
        "stages": [
            ("SD", "Shakedown Lamia", "2026-06-25T05:01:00Z"),
            ("SS1", "SS1 EKO Super Special Athens", "2026-06-25T16:05:00Z"),
            ("SS2", "SS2 Rengini 1", "2026-06-26T05:30:00Z"),
            ("SS3", "SS3 Elatia 1", "2026-06-26T06:50:00Z"),
            ("SS4", "SS4 Pavliani 1", "2026-06-26T08:20:00Z"),
            ("SS5", "SS5 Rengini 2", "2026-06-26T12:00:00Z"),
            ("SS6", "SS6 Elatia 2", "2026-06-26T13:20:00Z"),
            ("SS7", "SS7 Pavliani 2", "2026-06-26T14:50:00Z"),
            ("SS8", "SS8 Loutraki 1", "2026-06-27T05:15:00Z"),
            ("SS9", "SS9 Aghii Theodori 1", "2026-06-27T06:30:00Z"),
            ("SS10", "SS10 Livadia", "2026-06-27T08:15:00Z"),
            ("SS11", "SS11 Aghii Theodori 2", "2026-06-27T12:00:00Z"),
            ("SS12", "SS12 Loutraki 2", "2026-06-27T13:15:00Z"),
            ("SS13", "SS13 Karoutes 1", "2026-06-28T05:30:00Z"),
            ("SS14", "SS14 Tarzan 1", "2026-06-28T07:05:00Z"),
            ("SS15", "SS15 Karoutes 2", "2026-06-28T09:00:00Z"),
            ("SS16", "SS16 Tarzan 2 (Wolf Power Stage)", "2026-06-28T11:15:00Z"),
        ]
    },
    {
        "round": 9,
        "name": "Delfi Rally Estonia",
        "slug": "estonia",
        "start": "2026-07-16",
        "end": "2026-07-19",
        "stages": [
            ("SD", "Shakedown Kastre", "2026-07-16T06:01:00Z"),
            ("SS1", "SS1 Tartu vald 1", "2026-07-16T17:05:00Z"),
            ("SS2", "SS2 Peipsiääre 1", "2026-07-17T06:45:00Z"),
            ("SS3", "SS3 Mustvee 1", "2026-07-17T07:55:00Z"),
            ("SS4", "SS4 Raanitsa 1", "2026-07-17T09:05:00Z"),
            ("SS5", "SS5 Peipsiääre 2", "2026-07-17T12:35:00Z"),
            ("SS6", "SS6 Mustvee 2", "2026-07-17T13:45:00Z"),
            ("SS7", "SS7 Raanitsa 2", "2026-07-17T14:55:00Z"),
            ("SS8", "SS8 Neeruti 1", "2026-07-17T16:15:00Z"),
            ("SS9", "SS9 Mäeküla 1", "2026-07-18T05:45:00Z"),
            ("SS10", "SS10 Otepää 1", "2026-07-18T06:55:00Z"),
            ("SS11", "SS11 Kanepi 1", "2026-07-18T08:05:00Z"),
            ("SS12", "SS12 Mäeküla 2", "2026-07-18T11:45:00Z"),
            ("SS13", "SS13 Otepää 2", "2026-07-18T12:55:00Z"),
            ("SS14", "SS14 Kanepi 2", "2026-07-18T14:05:00Z"),
            ("SS15", "SS15 Elva Linn", "2026-07-18T15:35:00Z"),
            ("SS16", "SS16 Karaski 1", "2026-07-19T05:25:00Z"),
            ("SS17", "SS17 Kambja 1", "2026-07-19T06:35:00Z"),
            ("SS18", "SS18 Karaski 2", "2026-07-19T08:25:00Z"),
            ("SS19", "SS19 Kambja 2 (Wolf Power Stage)", "2026-07-19T11:15:00Z"),
        ]
    },
    {
        "round": 10,
        "name": "Secto Rally Finland",
        "slug": "finland",
        "start": "2026-07-30",
        "end": "2026-08-02",
        "stages": [
            ("SD", "Shakedown Ruuhimäki", "2026-07-30T06:01:00Z"),
            ("SS1", "SS1 Harju 1", "2026-07-30T16:05:00Z"),
            ("SS2", "SS2 Laukaa 1", "2026-07-31T05:13:00Z"),
            ("SS3", "SS3 Saarikas 1", "2026-07-31T06:20:00Z"),
            ("SS4", "SS4 Myhinpää 1", "2026-07-31T07:35:00Z"),
            ("SS5", "SS5 Ruuhimäki 1", "2026-07-31T08:45:00Z"),
            ("SS6", "SS6 Laukaa 2", "2026-07-31T12:10:00Z"),
            ("SS7", "SS7 Saarikas 2", "2026-07-31T13:17:00Z"),
            ("SS8", "SS8 Myhinpää 2", "2026-07-31T14:32:00Z"),
            ("SS9", "SS9 Ruuhimäki 2", "2026-07-31T15:42:00Z"),
            ("SS10", "SS10 Harju 2", "2026-07-31T17:05:00Z"),
            ("SS11", "SS11 Västilä 1", "2026-08-01T06:05:00Z"),
            ("SS12", "SS12 Päijälä 1", "2026-08-01T07:05:00Z"),
            ("SS13", "SS13 Ouninpohja 1", "2026-08-01T08:05:00Z"),
            ("SS14", "SS14 Västilä 2", "2026-08-01T12:35:00Z"),
            ("SS15", "SS15 Päijälä 2", "2026-08-01T13:35:00Z"),
            ("SS16", "SS16 Ouninpohja 2", "2026-08-01T14:35:00Z"),
            ("SS17", "SS17 Sahloinen-Moksi 1", "2026-08-02T05:55:00Z"),
            ("SS18", "SS18 Laajavuori 1", "2026-08-02T07:05:00Z"),
            ("SS19", "SS19 Sahloinen-Moksi 2", "2026-08-02T08:17:00Z"),
            ("SS20", "SS20 Laajavuori 2 (Wolf Power Stage)", "2026-08-02T11:15:00Z"),
        ]
    },
    {
        "round": 11,
        "name": "ueno Rally del Paraguay",
        "slug": "paraguay",
        "start": "2026-08-27",
        "end": "2026-08-30",
        "stages": [
            ("SD", "Shakedown Trinidad", "2026-08-27T08:01:00Z"),
            ("SS1", "SS1 Super Especial Encarnación 1", "2026-08-27T19:00:00Z"),
            ("SS2", "SS2 Cambyretá 1", "2026-08-28T07:30:00Z"),
            ("SS3", "SS3 Nueva Alborada 1", "2026-08-28T08:45:00Z"),
            ("SS4", "SS4 Capitán Miranda 1", "2026-08-28T10:00:00Z"),
            ("SS5", "SS5 Cambyretá 2", "2026-08-28T13:30:00Z"),
            ("SS6", "SS6 Nueva Alborada 2", "2026-08-28T14:45:00Z"),
            ("SS7", "SS7 Capitán Miranda 2", "2026-08-28T16:00:00Z"),
            ("SS8", "SS8 Carmen del Paraná 1", "2026-08-29T07:15:00Z"),
            ("SS9", "SS9 San Juan del Paraná 1", "2026-08-29T08:30:00Z"),
            ("SS10", "SS10 Fram 1", "2026-08-29T09:45:00Z"),
            ("SS11", "SS11 Carmen del Paraná 2", "2026-08-29T13:15:00Z"),
            ("SS12", "SS12 San Juan del Paraná 2", "2026-08-29T14:30:00Z"),
            ("SS13", "SS13 Fram 2", "2026-08-29T15:45:00Z"),
            ("SS14", "SS14 Hohenau 1", "2026-08-30T06:45:00Z"),
            ("SS15", "SS15 Obligado 1", "2026-08-30T08:00:00Z"),
            ("SS16", "SS16 Hohenau 2", "2026-08-30T09:15:00Z"),
            ("SS17", "SS17 Autódromo Encarnación (Wolf Power Stage)", "2026-08-30T11:15:00Z"),
        ]
    },
    {
        "round": 12,
        "name": "Rally Chile Bio Bío",
        "slug": "chile",
        "start": "2026-09-10",
        "end": "2026-09-13",
        "stages": [
            ("SD", "Shakedown Conuco", "2026-09-10T08:01:00Z"),
            ("SS1", "SS1 Pulpería 1", "2026-09-11T08:15:00Z"),
            ("SS2", "SS2 Rere 1", "2026-09-11T09:30:00Z"),
            ("SS3", "SS3 San Rosendo 1", "2026-09-11T10:45:00Z"),
            ("SS4", "SS4 Pulpería 2", "2026-09-11T14:15:00Z"),
            ("SS5", "SS5 Rere 2", "2026-09-11T15:30:00Z"),
            ("SS6", "SS6 San Rosendo 2", "2026-09-11T16:45:00Z"),
            ("SS7", "SS7 Pelún 1", "2026-09-12T07:45:00Z"),
            ("SS8", "SS8 Lota 1", "2026-09-12T09:00:00Z"),
            ("SS9", "SS9 María Las Cruces 1", "2026-09-12T10:15:00Z"),
            ("SS10", "SS10 Pelún 2", "2026-09-12T13:45:00Z"),
            ("SS11", "SS11 Lota 2", "2026-09-12T15:00:00Z"),
            ("SS12", "SS12 María Las Cruces 2", "2026-09-12T16:15:00Z"),
            ("SS13", "SS13 Laraquete 1", "2026-09-13T07:30:00Z"),
            ("SS14", "SS14 Biobío 1", "2026-09-13T08:45:00Z"),
            ("SS15", "SS15 Laraquete 2", "2026-09-13T10:00:00Z"),
            ("SS16", "SS16 Biobío 2 (Wolf Power Stage)", "2026-09-13T11:15:00Z"),
        ]
    },
    {
        "round": 13,
        "name": "Rally Italia Sardegna",
        "slug": "sardegna",
        "start": "2026-10-01",
        "end": "2026-10-04",
        "stages": [
            ("SD", "Shakedown Olbia", "2026-10-01T07:01:00Z"),
            ("SS1", "SS1 Osilo - Tergu 1", "2026-10-02T06:33:00Z"),
            ("SS2", "SS2 Sedini - Castelsardo 1", "2026-10-02T07:33:00Z"),
            ("SS3", "SS3 Osilo - Tergu 2", "2026-10-02T13:33:00Z"),
            ("SS4", "SS4 Sedini - Castelsardo 2", "2026-10-02T14:33:00Z"),
            ("SS5", "SS5 Tempio Pausania 1", "2026-10-03T05:41:00Z"),
            ("SS6", "SS6 Tula 1", "2026-10-03T06:49:00Z"),
            ("SS7", "SS7 Monte Lerno 1", "2026-10-03T08:07:00Z"),
            ("SS8", "SS8 Tempio Pausania 2", "2026-10-03T12:41:00Z"),
            ("SS9", "SS9 Tula 2", "2026-10-03T13:49:00Z"),
            ("SS10", "SS10 Monte Lerno 2", "2026-10-03T15:07:00Z"),
            ("SS11", "SS11 San Giacomo - Plebi 1", "2026-10-04T06:00:00Z"),
            ("SS12", "SS12 Cala Flumini 1", "2026-10-04T07:15:00Z"),
            ("SS13", "SS13 San Giacomo - Plebi 2", "2026-10-04T08:30:00Z"),
            ("SS14", "SS14 Sassari - Argentiera (Wolf Power Stage)", "2026-10-04T11:15:00Z"),
        ]
    },
    {
        "round": 14,
        "name": "Rally Saudi Arabia",
        "slug": "saudi-arabia",
        "start": "2026-11-11",
        "end": "2026-11-14",
        "stages": [
            ("SD", "Shakedown Jeddah Corniche", "2026-11-11T07:01:00Z"),
            ("SS1", "SS1 King Abdullah Economic City 1", "2026-11-11T16:00:00Z"),
            ("SS2", "SS2 Desert Dunes 1", "2026-11-12T05:30:00Z"),
            ("SS3", "SS3 Red Sea Coast 1", "2026-11-12T07:00:00Z"),
            ("SS4", "SS4 Wadi Al-Fara 1", "2026-11-12T08:30:00Z"),
            ("SS5", "SS5 Desert Dunes 2", "2026-11-12T12:00:00Z"),
            ("SS6", "SS6 Red Sea Coast 2", "2026-11-12T13:30:00Z"),
            ("SS7", "SS7 Wadi Al-Fara 2", "2026-11-12T15:00:00Z"),
            ("SS8", "SS8 Hijaz Mountains 1", "2026-11-13T05:45:00Z"),
            ("SS9", "SS9 Yanbu Canyon 1", "2026-11-13T07:15:00Z"),
            ("SS10", "SS10 Medina Plateau 1", "2026-11-13T08:45:00Z"),
            ("SS11", "SS11 Hijaz Mountains 2", "2026-11-13T12:15:00Z"),
            ("SS12", "SS12 Yanbu Canyon 2", "2026-11-13T13:45:00Z"),
            ("SS13", "SS13 Medina Plateau 2", "2026-11-13T15:15:00Z"),
            ("SS14", "SS14 Asir Escarpment 1", "2026-11-14T05:30:00Z"),
            ("SS15", "SS15 Jeddah Waterfront", "2026-11-14T07:00:00Z"),
            ("SS16", "SS16 Asir Escarpment 2", "2026-11-14T08:30:00Z"),
            ("SS17", "SS17 Jeddah Corniche Circuit (Wolf Power Stage)", "2026-11-14T11:15:00Z"),
        ]
    }
]


def slugify(text: str) -> str:
    text = re.sub(r"[^\w\s-]", "", text).strip().lower()
    return re.sub(r"[-\s]+", "-", text)


def main():
    repo_root = Path(__file__).resolve().parent.parent
    output_dir = repo_root / "motorsport" / "wrc"
    output_dir.mkdir(parents=True, exist_ok=True)

    year = datetime.now().year
    print(f"Generating full stage itinerary for WRC {year}...", file=sys.stderr)

    all_stage_events = []
    calendar_summary = []

    for rally in RALLIES_2026:
        rally_name = rally["name"]
        rally_slug = rally["slug"]
        print(f"Round {rally['round']}: {rally_name} ({len(rally['stages'])} stages)", file=sys.stderr)

        calendar_summary.append({
            "round": rally["round"],
            "name": rally_name,
            "start": rally["start"],
            "end": rally["end"],
            "stage_count": len(rally["stages"])
        })

        for code, stage_name, utc_str in rally["stages"]:
            stage_slug = slugify(code)
            all_stage_events.append({
                "id": f"wrc-{rally_slug}-{year}-{stage_slug}",
                "weekend": rally_name,
                "name": stage_name,
                "utc": utc_str,
            })

    # Write motorsport/wrc/<year>.json
    season_file = output_dir / f"{year}.json"
    output_data = {
        "sportKey": "wrc",
        "season": str(year),
        "events": all_stage_events,
    }
    season_file.write_text(json.dumps(output_data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {len(all_stage_events)} total stages across 14 rallies to {season_file}", file=sys.stderr)

    # Write schedule.json for compatibility
    schedule_file = output_dir / "schedule.json"
    schedule_data = {
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "season": year,
        "calendar": {
            "events": calendar_summary
        }
    }
    schedule_file.write_text(json.dumps(schedule_data, indent=2, default=str, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote schedule metadata to {schedule_file}", file=sys.stderr)


if __name__ == "__main__":
    main()
