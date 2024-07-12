"""Super Check Partial"""

# pylint: disable=unused-argument

import logging
import sqlite3
from pathlib import Path
from rapidfuzz import fuzz
from rapidfuzz import process

if __name__ == "__main__":
    print("I'm not the program you are looking for.")

logger = logging.getLogger("super_check_partial")
def prefer_prefix_score(query: str, candidate: str, **kwargs) -> int:
    """Return a score based on the quality of the match."""
    score = 0.5 * fuzz.ratio(query, candidate) + 0.5 * fuzz.partial_ratio(
        query, candidate
    )
    if not candidate.startswith(query):
        score = 0.8 * score
    return int(round(score))


class SCP_DB:
    """Super check partial"""

    def __init__(self, app_data_path):
        """initialize dialog"""
        self.scp = []
        self.app_data_path = app_data_path
        self.conn = sqlite3.connect(Path("{0}/{1}".format(self.app_data_path,"qrz.db")))
        self.cursor = self.conn.cursor()
        #Change default results from tuple to list to speedup the process
        self.cursor.row_factory = lambda cursor, row: "{0:<13} | {1}".format(row[0],row[1])

    def super_check(self, acall: str) -> list:
        """
        Performs a supercheck partial on the callsign entered in the field.
        """
        logger.debug("===================================================== Inside super check {0}".format(acall))
        if len(acall) > 2:
            self.cursor.execute('SELECT callsign,comments FROM qrz WHERE callsign LIKE "{0}%"'.format(acall))
            callsign_list = []
            comments_list = []
            results = self.cursor.fetchall()
            #for row in self.cursor.fetchall():
            #    callsign_list.append(row[0])
            #    comments_list.append(row[1])
            #logger.debug("===================================================== Inside super check results {0}".format(callsign_list))
            #logger.debug("===================================================== Inside super check comments {0}".format(comments_list))
            #return (callsign_list, comments_list)
            return results
        #return ([],[])
        return []
