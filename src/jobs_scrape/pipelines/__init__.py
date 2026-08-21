"""Chaine de traitement appliquee a chaque offre collectee.

L'ordre, fixe dans ``settings.py``, obeit a une logique simple : rendre l'offre
comparable (normalisation), s'assurer qu'elle est exploitable (validation),
ecarter ce qu'on connait deja (deduplication), et seulement ensuite depenser du
travail dessus (enrichissement) avant de l'ecrire.

Enrichir avant de dedupliquer reviendrait a analyser plusieurs fois la meme
annonce -- et, avec le greffon fonde sur un modele de langage, a payer plusieurs
fois pour le meme resultat.
"""
