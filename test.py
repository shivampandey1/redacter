import ast
import astor
import time
import logging
import vercel_ai

#####################
# function parsing

def get_function_info(node):
    function_info = {}
    function_info['name'] = node.name
    function_info['parameters'] = [arg.arg for arg in node.args.args]
    function_info['body'] = [ast.dump(n) for n in node.body]
    return function_info

class FunctionVisitor(ast.NodeVisitor):
    def __init__(self):
        self.functions = []

    def visit_FunctionDef(self, node):
        self.functions.append(get_function_info(node))
        self.generic_visit(node)

def function_parser(code):
    tree = ast.parse(code)
    visitor = FunctionVisitor()
    visitor.visit(tree)
    return visitor.functions

#######################
# gpt interaction

def ask_gpt_3_5(prompt, params, max_retries, delay_seconds):
    #vercel_ai.logger.setLevel(logging.INFO)
    client = vercel_ai.Client()
    
    explanation = ""
    retries = 0
    while retries <= max_retries:
        try:
            for chunk in client.generate("openai:gpt-3.5-turbo", prompt, params=params):
                explanation += chunk
            # output model response
            return explanation
        except Exception as e:
            retries += 1
            print(f"vercel error occurred: {e}. trying again ({retries}/{max_retries})")
            time.sleep(delay_seconds)

def generate_function_explanations(function_data):
    for function in function_data:
        name = function['name']
        params = function['parameters']
        body = function['body']
        
        # prompt for redacting functions
        prompt = (f"Explain the Python function {name} with parameters {params} and body {body}. "
                "Provide only the following sections:\n"
                "- Purpose: Explain what the function does in one sentence.\n"
                "- Contract: Describe the function signature, including input types and output types.\n"
                "- Effects: State any side effects or modifications the function makes.")
        
        # controlling response length just in case
        api_params = {"maximumLength":5000}
        
        # getting function explanation
        explanation = ask_gpt_3_5(prompt, api_params, 3, 3)
        
        # store the explanation into dict of ast function nodes
        function['explanation'] = explanation

    return function_data

#####################################
# function replacement

class FunctionBodyReplacer(ast.NodeTransformer):
    def __init__(self, function_data):
        self.function_data = {f["name"]: f["explanation"] for f in function_data}

    def visit_FunctionDef(self, node):
        explanation = self.function_data.get(node.name)
        if explanation:
            # replacing function body with the function explanation
            new_node = ast.copy_location(
                ast.FunctionDef(
                    name=node.name,
                    args=node.args,
                    body=[ast.Return(value=ast.Str(s=explanation))],
                    decorator_list=node.decorator_list,
                    returns=node.returns,
                ),
                node
            )
            return new_node
        return node

def replace_function_bodies_with_explanations(source_code, function_data):
    tree = ast.parse(source_code)
    replacer = FunctionBodyReplacer(function_data)
    new_tree = replacer.visit(tree)
    # converting ast tree back to code
    new_source_code = astor.to_source(new_tree) 
    return new_source_code

#####################################
if __name__ == "__main__":
    source_code = '''
def foo(x, y):
    return x + y

def bar(a, b):
    return a * b
'''
    parsed_functions = function_parser(source_code)
    function_data = generate_function_explanations(parsed_functions)
    new_source_code = replace_function_bodies_with_explanations(source_code, function_data)
    print("updated source code:")
    print(new_source_code)
