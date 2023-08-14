#!/usr/bin/env python3

import re
import argparse

import genanki
from pypdf import PdfReader

class Question:
    def __init__(self, q_t: tuple, category:str, q_num: int) -> None:
        self.ans = str(q_t[0]).strip()

        if self.ans.isdigit():
            self.type = "choice"
            self.options = list(q_t[2:6])
        else:
            self.type = "yesno"
            self.options = None
        
        self.category = category
        self.quiz_num = str(q_num)
        self.desc = q_t[1]        
        self.ref = q_t[-1]
    
    @staticmethod
    def htmltag(tag, text) -> str:
        return "<" + tag + ">" +  text + "</" + tag + ">"

    def get_category(self) -> str:
        if self.type == "choice":
            return self.category + "_選擇題"
        else:
            return self.category + "_是非題"

    def get_quiz_num(self) -> str:
        return self.quiz_num

    def get_quiz(self) -> str:
        if self.type == "choice":
            q_s = "(&ensp;)" + Question.htmltag('strong', self.desc) + "<hr>"
            for n, o in enumerate(self.options, start=1):
                n = str(n)
                q_s = q_s +  '(' + n + ')' + o + '<br>'
            return q_s
        else:
            # yes no question
            return "(&ensp;)" + Question.htmltag('strong', self.desc)       

    def get_ans(self) -> str: 
        if self.type == "choice": 
            # repeat question
            ans_s = "(" + self.ans + ")" + Question.htmltag('strong', self.desc) + "<hr id=answer>"      

            for n, o in enumerate(self.options, start=1):
                n = str(n)
                if n == self.ans:
                    ans_s = ans_s + Question.htmltag('b', '(' + n + ')' + o ) + '<br>'
                else:
                    ans_s = ans_s +  '(' + n + ')' + o + '<br>'
        else:
            # yes no question
            # repeat question, but fill in the answer
            ans_s = "( " + self.ans + " )" + Question.htmltag('strong', self.desc) + "<hr id=answer>" + self.ans + "<br>"          
        
        if self.ref:
            ans_s = ans_s +  '<br>依據法源: ' + self.ref 

        return ans_s        
    
def tokenize_quiz(re_str, text, cat, q_num):
    if re.search(re_str, text):
        return Question(re.search(re_str, text).groups(), cat, q_num)
    else:
        return None 

def get_title_span(text: str):
    re_title_row = re.compile('編\n號答\n案試題( 依據法源)?\n', re.MULTILINE)
    
    if(re_title_row.search(text)):
        return re_title_row.search(text).span()
    
    return None

def get_quiz_info(text: str, info: dict) -> dict:
    text_info = re.search('\n?(?P<category>.+)\n(?P<quiz_type>選擇題|是非題)', text, re.MULTILINE)
    
    #TODO: category may vary by time, output fail to match for manual checking
    all_category = ["政府採購全生命週期概論", "政府採購法之總則、招標及決標", "政府採購法之罰則及附則",
                    "政府採購法之履約管理及驗收", "政府採購法之爭議處理", "底價及價格分析", 
                    "投標須知及招標文件製作", "採購契約", "最有利標及評選優勝廠商", "電子採購實務",
                    "工程及技術服務採購作業", "財物及勞務採購作業", "錯誤採購態樣", "道德規範及違法處置"]
    
    # Always choice first, yesno second
    # There is no category string before yesno question    
    if text_info.group('quiz_type'):
        info['quiz_type'] = text_info.group('quiz_type').strip()

        if text_info.group('category').strip() in all_category:
            info['category'] = text_info.group('category').strip()
        else:
            pass
            # Debug: uncomment this if fail to match category, or some quiz didn't correctly parse
            # print("\t Fail to match category, may due to source change, need manual verify")
            # print("\t" + text_info.group('category').strip())
    else:
        raise ValueError("Fail to parse quiz info!")

    return info


def extract_next_page(reader: PdfReader, index: int) -> tuple:
    try:
        return (True, reader.pages[index].extract_text())
    except IndexError:
        return (False, None)

def set_re_patten(quiz_type: str, q_num: int):
        
        # choice
        if quiz_type == "選擇題":
            raw_choice_patten = re.compile('(?P<quiz>'+ str(q_num)+'[1-4].+\(1\).+\(2\).+\(3\).+\(4\).+)\n' + str(q_num + 1) +'[1-4]', flags=re.MULTILINE | re.DOTALL)
            re_choice = re.compile(str(q_num) + '(?P<ans>[1-4])(?P<quiz>.+?)\(1\)(?P<option1>.+?)\(2\)(?P<option2>.+?)\(3\)(?P<option3>.+?)\(4\)(?P<option4>.+?)(?P<law>第 \d* 條|綜合)?$', flags = re.MULTILINE | re.DOTALL)
            
            return (raw_choice_patten, re_choice)
         
        # yesno or fallback for page 1
        raw_yesno_patten = re.compile('(?P<quiz>'+ str(q_num)+'[OX].+)\n' + str(q_num + 1) +'[OX]', flags = re.MULTILINE | re.DOTALL)
        re_yesno = re.compile(str(q_num) + '(?P<ans>[OX])(?P<quiz>.+?)(?P<law>第 \d* 條|綜合)?$', flags = re.MULTILINE | re.DOTALL) 

        return (raw_yesno_patten, re_yesno)

re_download_date = re.compile('資料產生日期：(?P<date>.+?)$', re.MULTILINE)

def parse_gpa_quiz(input_filepath: str, output_filepath: str):
    
    # Open pdf file
    reader = PdfReader(input_filepath)

    total_pages = len(reader.pages)
    category = ''
    quiz_type = ''
    quizs = list()

    first_page_text = reader.pages[0].extract_text()
    # Parse download date, only for page 1
    if(re_download_date.search(first_page_text)):
        download_date = re_download_date.search(first_page_text).group('date').replace("/","-")

    text_main = ''
    text_next_type = ''
    info_next = {"category": '', "quiz_type": ''}

    # Flow:
    ## Split text extracted from page to current(append to current) and next by titlerow 
    ## Analysis category and quiz type in current text, Set Flag_analy to False
    ## Remove Title row
    ## Start to parse
    ## if search to the end, fail to search, load next page, 
    ## split: Sucess, append same category/ quiz type to current, use flag to mark Analysis on next fail, Fail: append all to current

    keep_search = False
    # load next page will add 1 to index
    page_index = -1
    q_num = 1
    start_pos = 0
    record_num = 0

    while page_index < total_pages:        
        while(keep_search):
 
            patten_obj, parse_obj = set_re_patten(quiz_type, q_num)

            try:
                s_res = patten_obj.search(text_main[start_pos: ])
                if s_res:
                    _, s_span = s_res.span()
                    # next start_pos should include q_num + 1
                    start_pos = start_pos + s_span - len(str(q_num + 1)) - 1
        
                    q_text = s_res.group('quiz').replace('\n','')                   
                    quizs.append(tokenize_quiz(parse_obj, q_text, category, q_num))
                    q_num = q_num +1
                else:
                    # Maybe end of page or no more same type question
                    # Leave for netxt part to parse
                    keep_search = False                
                
            except Exception as e:
                print(e)
                print(q_num)                

        if not keep_search:
            # load next page or text type question
            if text_next_type:
                # No more same type question, do last match
                start_pos = start_pos - len(str(q_num + 1)) - 1
                last_quiz = tokenize_quiz(parse_obj, text_main[start_pos: ].replace('\n',''), category, q_num)

                if last_quiz:
                    quizs.append(last_quiz)
                elif category:
                    # ignore first time parse, which category is None
                    print("Fail to match Last Question")
                    print(category + quiz_type + '_' + str(q_num))
                    #print(text_main[start_pos: ])

                if category:
                    # ignore first time parse, which category is None
                    print("Parse: " + category + '_' + quiz_type)
                    print("Count: " + str(q_num))

                record_num = record_num + q_num

                category = info_next["category"]
                quiz_type =  info_next["quiz_type"]
                text_main = text_next_type
                text_next_type = ''
                keep_search = True
                start_pos = 0
                q_num = 1
            else:
                # Load next page
                page_index = page_index + 1
                keep_search, raw_text = extract_next_page(reader, page_index)

                # Next page existed
                if keep_search:
                    # Remove title row
                    ## Appear on first page, and middle of other pages
                    ## Always choice first, yesno second
                    if get_title_span(raw_text):
                        backward_pos, new_quiz_start_pos = get_title_span(raw_text)
                        # TODO: ugly code
                        try:
                            info_next = get_quiz_info('\n'.join(raw_text[ :backward_pos].splitlines()[-2:]), info_next)
                        except AttributeError:
                            # Title maybe on the page top, faile to parse category
                            # fallback with textmain last few lines
                            merge_page = text_main.splitlines()[-3:] + raw_text[ :backward_pos].splitlines()[-2:]
                            info_next = get_quiz_info('\n'.join(merge_page), info_next)
                        # Remove category and quiz type
                        ## \n for re match
                        ## yesno question don't have category                    
                        back_index = 2
                        if info_next["quiz_type"] == "是非題":
                            back_index = 1
                        text_main = text_main + '\n' + '\n'.join(raw_text[ :backward_pos].splitlines()[: -back_index])
                        text_next_type = raw_text[new_quiz_start_pos: ]
                    else:
                        # \n for re match
                        text_main = text_main + '\n' + raw_text
                else:
                    # End of pdf, do last match
                    start_pos = start_pos - len(str(q_num + 1)) - 1
                    last_quiz = tokenize_quiz(parse_obj, text_main[start_pos: ].replace('\n',''), category, q_num)

                    if last_quiz:
                        quizs.append(last_quiz)
                        #print(last_quiz)
                    else:
                        print("fail to Find Last Quiz ")

    print("Parse: " + category + '_' + quiz_type)
    print("Count: " + str(q_num))
    record_num = record_num + q_num
  
    # Generate Anki package
    # ref: https://github.com/kerrickstaley/genanki
    # more details: https://docs.ankiweb.net/
    gpa_deck = genanki.Deck(1614529274, '採購法題庫_' + download_date)
    
    gpa_model = genanki.Model(
        1472238217, '採購法',
        fields = [
            {'name': 'Question'},
            {'name': 'Answer'},
            {'name': 'QuestionNumber'},
        ],
        templates = [
            {
            'name': 'GPA Quiz',
            'qfmt': '{{Question}}',
            'afmt': '{{Answer}}',
            }        
        ],
        css = ".card{background: #EAFFD0; font-size: 4vh;}"
    )

    for q in quizs:
        gpa_deck.add_note(
            genanki.Note(model=gpa_model, 
                         fields=[q.get_quiz(), q.get_ans(), q.get_quiz_num()],
                         tags=[q.get_category()])
        )
        
    print("\n Total Quiz: " + str(len(quizs)))

    genanki.Package(gpa_deck).write_to_file(output_filepath)
    
if __name__ == '__main__':

    parser = argparse.ArgumentParser()
    parser.add_argument("-i", "--input_file_path", dest="input_path",\
                        help="input pdf file path")
    parser.add_argument("-o", "--output_file_path", dest="output_path",\
                        help="output file path, ex. gpa.apkg")
    args = parser.parse_args()

    parse_gpa_quiz(args.input_path, args.output_path)