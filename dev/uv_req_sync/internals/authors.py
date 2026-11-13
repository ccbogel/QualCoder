from sys import exit


def show_authors(author_list:list[dict]) ->None:
    for i in author_list:
        print(f"{i}) {i["name"]}")

def authors_processing(author_list:list[dict])->list[dict]:
    """
    A recurring function that returns a list with the dict info of each developer
    it only exits when the user exits by "keeping the list as is"
    """
    test=input(f"""
    The project currently has currently {len(author_list)} authors
    {show_authors(author_list)}
    What would you like to do?

    1) Keep as is (default)
    2) Add one?
    3) Remove one?
    4) Exit Programm?
    """)

    match test:
        case 1 | "1" | None:
            return author_list
        case 4 | "4":
            print("Exiting programm")
            exit(0)
        case 3 | "3":
            to_pop_i:str=input("Which one would you like to remove?\n")
            try:
                to_pop_int = int(to_pop_i)
                final_check=input(f"""
                This action will delete {author_list[to_pop_int].get("name")} from the metadata. 
                This cannot be undone and will require for you to recreate the entry.
                Would you like to proceed?
                (Y)es (N)o (Default is no)
                """)
                if final_check.lower() == "y":
                    author_list.pop(to_pop_int)
                authors_processing(author_list)
            except (TypeError, IndexError) as e:
                if e == TypeError:
                    print(f"{e}: {to_pop_i} is not an integer")
                elif e == IndexError:
                    print(f"{e}: There is no author for index {to_pop_int}")
                authors_processing(author_list)
        case 2 | "2":
            add_mode=input("""
            What would you like to do?

            1) Append another author to the end?
            2) Add the author to a specific position?
            """)

            author_name=input("Add the Name:\n")

            dict={
                "name": author_name
            }

            email_check=input(f"Would you like to add an e-mail for {author_name}?\n (Y)es (N)o\n(Default is no)\n")
            if email_check.lower() == "y":
                dict={
                "name": author_name,
                "email": input("What it the authors email?")
                }  
            
            if add_mode in [1, "1"]:
                author_list.append(dict)
            elif add_mode in [2, "2"]:
                
                try:
                    pos_to_add=input("In what position would you like to add the entry?\n(Index is 0 based)")
                    author_list.insert(int(pos_to_add),dict)
                except (TypeError, IndexError) as e:
                    if e == TypeError:
                        print(f"{e}:{pos_to_add} is not an integer")
                    elif e == IndexError:
                        print(f"{e}: Invalid index for {pos_to_add}")
                    authors_processing(author_list)
            else:
                print("Unrecognized option")
            authors_processing(author_list)
        
        case r"*":
            print(f"{test} is not a valid option")
            authors_processing(author_list)

    return author_list