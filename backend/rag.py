from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import re

from vectordb import LocalVectorDB


@dataclass
class IngestionPayload:
    language: str
    title: str
    code_fragment: str
    explanation: str
    tags: list[str]


class LanguageDetector:
    """Enhanced language detection with priority-based matching."""
    
    PYTHON_INDICATORS = [
        "def ", "self", "import ", "from ", "None", "async def", 
        "print(", "lambda ", "if __name__", "elif ", "else:"
    ]
    
    CPP_INDICATORS = [
        "std::", "cout", "cin", "namespace", "template<", 
        "using namespace", "class ", "public:", "private:", "::"
    ]
    
    C_INDICATORS = [
        "printf", "scanf", "#include <stdio.h>", "#include <stdlib.h>",
        "malloc", "free", "calloc", "realloc"
    ]

    def detect(self, code: str) -> str:
        """Detect programming language with improved accuracy."""
        lowered = code.lower()
        
        # Python detection (most distinct syntax)
        if any(indicator.lower() in lowered for indicator in self.PYTHON_INDICATORS):
            # Verify it's not C++ with class syntax
            if "class " in code and "{" in code and "::" in code:
                return "c++"
            return "python"
        
        # C++ specific features (check before C)
        if any(indicator.lower() in lowered for indicator in self.CPP_INDICATORS):
            return "c++"
        
        # C-only features
        if any(indicator.lower() in lowered for indicator in self.C_INDICATORS):
            return "c"
        
        # Generic C/C++ patterns
        if "#include" in code:
            # C++ has class with braces, namespaces, or templates
            if ("class " in code and "{" in code) or "namespace" in code or "template" in code:
                return "c++"
            # Default to C for simple includes
            return "c"
        
        # Python class syntax (no braces)
        if "class " in code and ":" in code and "{" not in code:
            return "python"
        
        # Default fallback
        return "c"


class CodeExplainerRAG:
    """RAG-based code explanation system with detailed analysis."""
    
    def __init__(self, data_path: Path, embedder_name: str) -> None:
        self.data_path = data_path
        self.detector = LanguageDetector()
        self.db = LocalVectorDB(data_path=data_path, embedder_name=embedder_name)

    def load(self) -> None:
        """Load the knowledge base and compute embeddings."""
        self.db.load()

    def explain(self, code: str, language_hint: Optional[str]) -> dict:
        """Generate detailed explanation of code with RAG context."""
        language = (language_hint or "").lower().strip() or self.detector.detect(code)
        
        # Enhanced search query
        search_query = f"{language} programming: {self._extract_keywords(code)} {code[:300]}"
        context = self.db.search(query=search_query, top_k=5)

        reasoning = [
            f"Detected language: {language}",
            f"Analyzed code structure: {self._analyze_structure(code)}",
            f"Retrieved {len(context)} reference snippet(s) from knowledge base",
        ]
        
        # Generate line-by-line explanations
        line_by_line = self._analyze_line_by_line(code, language, context)
        
        if not context:
            reasoning.append("No close references found, using heuristic analysis.")
            summary = self._detailed_fallback_explanation(language, code)
            return {
                "language": language,
                "summary": summary,
                "reasoning": reasoning,
                "line_by_line": line_by_line,
                "references": []
            }

        # Generate detailed explanation
        detailed_analysis = self._generate_detailed_explanation(code, language, context)
        
        return {
            "language": language,
            "summary": detailed_analysis["summary"],
            "reasoning": reasoning + detailed_analysis["analysis_steps"],
            "line_by_line": line_by_line,
            "references": context[:3]  # Top 3 most relevant
        }

    def _analyze_line_by_line(self, code: str, language: str, context: list[dict]) -> list[dict]:
        """Analyze code line by line with detailed explanations."""
        lines = code.split('\n')
        explanations = []
        line_num = 1
        
        # Build context knowledge for better explanations
        context_keywords = {}
        for item in context:
            if item.get('code_fragment'):
                context_keywords.update(self._extract_code_patterns(item['code_fragment']))
        
        for i, line in enumerate(lines):
            stripped = line.strip()
            
            # Skip empty lines but keep them for line numbering
            if not stripped:
                explanations.append({
                    "line_number": line_num,
                    "code": line,
                    "explanation": "Empty line (whitespace for readability)"
                })
                line_num += 1
                continue
            
            # Skip comment-only lines but explain them
            if self._is_comment_only(stripped, language):
                explanations.append({
                    "line_number": line_num,
                    "code": line,
                    "explanation": self._explain_comment(stripped, language)
                })
                line_num += 1
                continue
            
            # Analyze the line
            explanation = self._explain_line(stripped, line, language, context_keywords, i, lines)
            explanations.append({
                "line_number": line_num,
                "code": line,
                "explanation": explanation
            })
            line_num += 1
        
        return explanations

    def _explain_line(self, stripped: str, original: str, language: str, 
                     context: dict, line_index: int, all_lines: list[str]) -> str:
        """Generate explanation for a single line of code."""
        explanations = []
        
        # Include directives
        if stripped.startswith("#include"):
            lib = stripped.replace("#include", "").strip().strip("<>\"")
            explanations.append(f"Includes the {lib} library, providing standard I/O functions")
            if "stdio.h" in lib:
                explanations.append("for input/output operations like printf and scanf")
            elif "stdlib.h" in lib:
                explanations.append("for memory management and utility functions")
        
        # Function definitions
        elif re.match(r'\s*(def|int|void|float|double|char|bool)\s+\w+\s*\(', stripped):
            func_match = re.search(r'(def|int|void|float|double|char|bool)\s+(\w+)\s*\(', stripped)
            if func_match:
                func_type = func_match.group(1)
                func_name = func_match.group(2)
                if func_type == "def":
                    explanations.append(f"Defines a Python function named '{func_name}'")
                else:
                    explanations.append(f"Defines a {func_type} function named '{func_name}'")
                
                # Check for parameters
                params = re.search(r'\(([^)]*)\)', stripped)
                if params and params.group(1).strip():
                    explanations.append(f"that takes parameters: {params.group(1).strip()}")
                else:
                    explanations.append("that takes no parameters")
        
        # Return statements
        elif stripped.startswith("return "):
            return_expr = stripped.replace("return", "").strip()
            if return_expr == "0":
                explanations.append("Returns 0 to indicate successful program termination")
            elif return_expr == "n" or return_expr in ["1", "-1"]:
                explanations.append(f"Returns the value {return_expr}, typically used as a base case or result")
            elif "fibonacci" in return_expr.lower() or "fib" in return_expr.lower():
                explanations.append("Recursively returns the sum of two previous Fibonacci numbers")
            else:
                explanations.append(f"Returns the result: {return_expr}")
        
        # Conditional statements
        elif stripped.startswith("if "):
            condition = stripped.replace("if", "").strip().strip("():")
            if "n <= 1" in condition or "n < 2" in condition:
                explanations.append("Base case check: if n is 0 or 1, return n directly")
                explanations.append("This prevents infinite recursion in Fibonacci calculation")
            elif "in " in condition and language == "python":
                explanations.append(f"Checks if an element exists in a collection: {condition}")
            else:
                explanations.append(f"Conditional check: {condition}")
                explanations.append("If true, executes the following block")
        
        # Variable declarations/assignments
        elif re.match(r'\s*(int|float|double|char|bool|var|let|const)\s+\w+', stripped):
            var_match = re.search(r'(int|float|double|char|bool|var|let|const)?\s*(\w+)\s*[=:]\s*(.+)', stripped)
            if var_match:
                var_type = var_match.group(1) or "variable"
                var_name = var_match.group(2)
                var_value = var_match.group(3).strip().rstrip(";")
                explanations.append(f"Declares {var_type} '{var_name}' and initializes it to {var_value}")
        
        # Loop constructs
        elif stripped.startswith("for ") or stripped.startswith("while "):
            if "for " in stripped:
                if "in range" in stripped:
                    explanations.append("Iterates over a range of numbers")
                elif "in " in stripped and language == "python":
                    explanations.append("Iterates over elements in a collection")
                else:
                    explanations.append("Traditional for loop with initialization, condition, and increment")
            else:
                explanations.append("While loop: continues executing while condition is true")
        
        # Print/output statements
        elif "printf" in stripped or "cout" in stripped or "print(" in stripped:
            if "printf" in stripped:
                explanations.append("Prints formatted output to the console")
            elif "cout" in stripped:
                explanations.append("C++ output stream: sends data to standard output")
            else:
                explanations.append("Python print function: displays output to console")
        
        # Recursive calls
        elif re.search(r'\w+\s*\([^)]*\)', stripped) and "=" not in stripped:
            func_call = re.search(r'(\w+)\s*\(', stripped)
            if func_call:
                func_name = func_call.group(1)
                if func_name in [line.split()[1].split("(")[0] for line in all_lines 
                                if re.match(r'\s*(def|int|void)\s+\w+', line)]:
                    explanations.append(f"Recursive call to '{func_name}' function")
                    explanations.append("This function calls itself with modified parameters")
        
        # Arithmetic operations
        elif any(op in stripped for op in ["+", "-", "*", "/", "%"]):
            if "fibonacci" in stripped.lower() or "fib" in stripped.lower():
                explanations.append("Calculates Fibonacci by summing two recursive calls")
                explanations.append("F(n) = F(n-1) + F(n-2)")
        
        # Default: analyze what the line does
        if not explanations:
            explanations.append(self._generic_line_explanation(stripped, language))
        
        return ". ".join(explanations) + "."

    def _is_comment_only(self, line: str, language: str) -> bool:
        """Check if line contains only comments."""
        stripped = line.strip()
        if language in ["c", "c++"]:
            return stripped.startswith("//") or stripped.startswith("/*")
        elif language == "python":
            return stripped.startswith("#")
        return False

    def _explain_comment(self, line: str, language: str) -> str:
        """Explain what a comment does."""
        comment_text = line.lstrip("#/").strip()
        if comment_text:
            return f"Comment: {comment_text}"
        return "Comment line for code documentation"

    def _extract_code_patterns(self, code: str) -> dict:
        """Extract common patterns from code for context."""
        patterns = {}
        if "recursive" in code.lower() or code.count("(") > 2:
            patterns["recursion"] = True
        if "for " in code or "while " in code:
            patterns["loops"] = True
        return patterns

    def _generic_line_explanation(self, line: str, language: str) -> str:
        """Generate generic explanation for unrecognized lines."""
        if "{" in line:
            return "Opens a code block"
        elif "}" in line:
            return "Closes a code block"
        elif ";" in line and language in ["c", "c++"]:
            return "Statement terminator (semicolon ends the statement)"
        elif ":" in line and language == "python":
            return "Python block indicator (colon starts a new block)"
        else:
            return f"Executes: {line[:50]}"

    def ingest(self, payload: IngestionPayload) -> None:
        """Add new code example to knowledge base."""
        self.db.add_entry(payload.__dict__)

    def _extract_keywords(self, code: str) -> str:
        """Extract meaningful keywords from code."""
        # Function/class names
        func_pattern = r'\b(def|function|int|void|class)\s+(\w+)'
        matches = re.findall(func_pattern, code)
        keywords = [match[1] for match in matches if len(match) > 1]
        
        # Algorithm names
        algo_keywords = ["sort", "search", "fibonacci", "graph", "tree", "hash", "stack", "queue"]
        found_algos = [kw for kw in algo_keywords if kw.lower() in code.lower()]
        
        return " ".join(keywords + found_algos)

    def _analyze_structure(self, code: str) -> str:
        """Analyze code structure and patterns."""
        features = []
        
        if re.search(r'\b(def|function|int|void)\s+\w+\s*\(', code):
            features.append("function definition")
        if "if " in code or "if(" in code:
            features.append("conditional logic")
        if "for " in code or "while " in code:
            features.append("loop construct")
        if "return " in code:
            features.append("return statement")
        if "class " in code:
            features.append("class definition")
        if "*" in code and ("int" in code or "char" in code):
            features.append("pointer usage")
        if "[" in code and "]" in code:
            features.append("array/indexing")
        
        return ", ".join(features) if features else "basic structure"

    def _generate_detailed_explanation(self, code: str, language: str, context: list[dict]) -> dict:
        """Generate comprehensive explanation using RAG context."""
        # Analyze what the code does
        intent = self._infer_intent(code)
        structure = self._analyze_code_structure(code, language)
        patterns = self._identify_patterns(code, language)
        
        # Build explanation from context
        context_insights = []
        for item in context[:3]:
            if item.get('explanation'):
                context_insights.append(item['explanation'])
        
        # Combine insights
        summary_parts = [
            f"This {language} code implements {intent}.",
            structure,
            patterns,
        ]
        
        if context_insights:
            summary_parts.append(
                f"Similar patterns in the knowledge base suggest: {'; '.join(context_insights[:2])}."
            )
        
        summary = " ".join(summary_parts)
        
        analysis_steps = [
            f"Identified primary purpose: {intent}",
            f"Code structure analysis: {self._analyze_structure(code)}",
            f"Pattern recognition: {patterns}",
        ]
        
        return {
            "summary": summary,
            "analysis_steps": analysis_steps
        }

    def _analyze_code_structure(self, code: str, language: str) -> str:
        """Analyze the structural elements of the code."""
        lines = code.strip().split('\n')
        non_empty = [l.strip() for l in lines if l.strip() and not l.strip().startswith('//')]
        
        structure_desc = []
        
        # Function analysis
        func_match = re.search(r'(def|int|void|function)\s+(\w+)\s*\(', code)
        if func_match:
            func_name = func_match.group(2)
            structure_desc.append(f"defines function '{func_name}'")
        
        # Recursion detection
        if func_match:
            func_name = func_match.group(2)
            if func_name in code.replace(func_match.group(0), "", 1):
                structure_desc.append("uses recursive calls")
        
        # Loop analysis
        if "for " in code or "while " in code:
            structure_desc.append("contains iterative loops")
        
        # Conditional analysis
        if_count = code.count("if ")
        if if_count > 0:
            structure_desc.append(f"has {if_count} conditional branch{'es' if if_count > 1 else ''}")
        
        return "The code " + ", ".join(structure_desc) + "." if structure_desc else ""

    def _identify_patterns(self, code: str, language: str) -> str:
        """Identify common programming patterns."""
        patterns = []
        lowered = code.lower()
        
        # Algorithm patterns
        if "fibonacci" in lowered or "fib" in lowered:
            patterns.append("Fibonacci sequence calculation")
        if "sort" in lowered:
            patterns.append("sorting algorithm")
        if "search" in lowered or "find" in lowered:
            patterns.append("search algorithm")
        if "graph" in lowered or "node" in lowered:
            patterns.append("graph data structure")
        
        # Design patterns
        if "class " in code and language in ["python", "c++"]:
            patterns.append("object-oriented design")
        if "template" in code:
            patterns.append("generic programming")
        if "*" in code and language in ["c", "c++"]:
            patterns.append("pointer manipulation")
        
        # Control flow patterns
        if "return " in code and code.count("return") > 1:
            patterns.append("early return pattern")
        if "if " in code and "else" in code:
            patterns.append("conditional branching")
        
        return "Identified patterns: " + ", ".join(patterns) if patterns else "Standard implementation pattern"

    @staticmethod
    def _infer_intent(code: str) -> str:
        """Infer the primary intent/purpose of the code."""
        lowered = code.lower()
        
        # Specific algorithms
        if "fibonacci" in lowered or "fib" in lowered:
            return "a recursive Fibonacci sequence generator that calculates the nth Fibonacci number using the mathematical relationship F(n) = F(n-1) + F(n-2) with base cases for n <= 1"
        
        if "quicksort" in lowered or ("sort" in lowered and "pivot" in lowered):
            return "the Quicksort algorithm, a divide-and-conquer sorting method that partitions arrays around a pivot element"
        
        if "mergesort" in lowered or ("sort" in lowered and "merge" in lowered):
            return "the Mergesort algorithm, which divides arrays into halves and merges sorted subarrays"
        
        if "binary" in lowered and "search" in lowered:
            return "binary search, an efficient O(log n) search algorithm for sorted arrays"
        
        # Data structures
        if "graph" in lowered or ("node" in lowered and "neighbor" in lowered):
            return "graph traversal, likely using depth-first or breadth-first search to visit all nodes"
        
        if "tree" in lowered and ("node" in lowered or "leaf" in lowered):
            return "tree data structure operations, such as traversal or node manipulation"
        
        if "stack" in lowered or ("push" in lowered and "pop" in lowered):
            return "stack data structure with LIFO (Last In First Out) operations"
        
        if "queue" in lowered or ("enqueue" in lowered and "dequeue" in lowered):
            return "queue data structure with FIFO (First In First Out) operations"
        
        # Common utilities
        if "swap" in lowered:
            return "a value swapping utility that exchanges two variables, often using temporary storage or pointer manipulation"
        
        if "reverse" in lowered:
            return "string or array reversal algorithm"
        
        if "factorial" in lowered or "fact" in lowered:
            return "factorial calculation, typically using recursion"
        
        # Memory management
        if "malloc" in lowered or "new " in lowered:
            return "dynamic memory allocation"
        
        if "free" in lowered or "delete " in lowered:
            return "memory deallocation and resource cleanup"
        
        # OOP patterns
        if "class " in code and ("__init__" in lowered or "constructor" in lowered):
            return "an object-oriented class definition with initialization logic"
        
        if "template" in code:
            return "generic programming using templates for type-independent code"
        
        # Control flow
        if "main()" in code or "int main" in code:
            return "a main program entry point that orchestrates function calls and program execution"
        
        # Default
        return "core algorithmic logic with specific computational steps"

    @staticmethod
    def _summarize_context(text: str) -> str:
        """Extract key insights from context text."""
        sentences = [s.strip() for s in text.split(".") if len(s.strip()) > 15]
        return "; ".join(sentences[:3]) if sentences else "general programming best practices"

    @staticmethod
    def _detailed_fallback_explanation(language: str, code: str) -> str:
        """Generate detailed explanation when no context is available."""
        intent = CodeExplainerRAG._infer_intent(code)
        structure = CodeExplainerRAG._analyze_structure(code)
        
        return (
            f"This {language} code implements {intent}. "
            f"The implementation uses {structure}. "
            f"While no exact matches were found in the knowledge base, the code follows standard {language} "
            f"conventions and demonstrates common programming patterns. "
            f"Key aspects include proper function definition, control flow management, and algorithmic logic."
        )