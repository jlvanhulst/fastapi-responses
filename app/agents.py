"""
Simple implementation of Agent and Runner classes to support PromptAgent.
"""

class Agent:
    """
    Base Agent class that PromptAgent inherits from.
    """
    def __init__(self, name, instructions=None, model=None, handoffs=None, output_type=None):
        self.name = name
        self.instructions = instructions
        self.model = model
        self.handoffs = handoffs or []
        self.output_type = output_type

class Runner:
    """
    Simple Runner class to execute prompts.
    """
    @staticmethod
    async def run(agent, prompt):
        """
        Run a prompt through an agent.
        
        Args:
            agent: The agent to run the prompt through.
            prompt: The prompt to run.
            
        Returns:
            The result of running the prompt.
        """
        return prompt
