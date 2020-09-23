import logging
from colorama import Style, Fore


SR = Style.RESET_ALL
NL = "\n"

class Logger:
    def __init__(self, filename):
        self.filename = filename
        with open(self.filename, "r") as file:
            self.code = file.readlines()
        
    def log(self, message, line=-1, char=-1, type_="info"):
        if type_ == "error":
            color = Fore.RED
        elif type_ == "warning":
            color = Fore.YELLOW
        else:
            color = ""
             
        if line == -1 and char == -1:
            logging.warning(f"{color}{type_.capitalize()}\n"
                            f"    File \"{self.filename}\"\n"
                            f"{message}{SR}")
            
        elif line != -1:
            if char == -1:
                logging.warning(f"{color}{type_.capitalize()}\n"
                                f"    File \"{self.filename}\" on line {line}\n"
                                f"{message}{SR}")
            else:
                logging.warning(f"{color}{type_.capitalize()}\n"
                                f"    File \"{self.filename}\" on line {line}\n"
                                f"        {self.code[line-1].replace(NL, '')}\n"
                                f"        {' '*char + '^'}\n"
                                f"{message}{SR}")
