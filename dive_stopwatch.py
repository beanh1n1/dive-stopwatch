print("test2")

# ---------- Imports ---------- 

from dataclasses import dataclass

# ---------- DivePhase Data Class ----------
@dataclass
class DivePhase:
    name: str           # Name of the dive phase (e.g., "Descent", "Bottom Time", "Ascent")
    start_time: float
    end_time: float
    notes: str = ""

    @property
    def duration(self) -> float:
        return self.end_time - self.start_time
    
# ---------- Stopwatch  ----------
class Stopwatch:
    def start () -> None:
    def stop () -> None:
    def reset () -> None:
    def lap () -> None:             # returns elapsed time at this moment
    def elapsed_time () -> float:   # returns total elapsed time

# ---------- DiveSession ----------
class DiveSession:
    def __init__(self, diver: str, depth: int):
    def start_phase(self, phase: str) -> None:
    def end_phase(self, notes: str = "") -> None:
    def get_phases(self) -> list[DivePhase]:
    def summary () -> dict
        
# ---------- DecompressionPlan 
class DecompressionPlan:
    def __init__(self, stops: list[DecoStop], max_depth: int):
   
   
    def delay(self, current_time: float, depth: int) -> bool:
    #check if planned time to first stop has elapsed

    def recompute(self, current_depth: int, elapsed: float) -> None:
    #recompute stop time based on current depth and elapsed time

        if self.delay(elapsed, current_depth) is True:
            # logic to adjust stop times based on current depth and elapsed time
            if self.delay <= 1 # delay < 1 minute, any depth
                pass
           
            if self.delay > 1 and current_depth < 50 # delay > 1 minute, shallower than 50fsw
                # round to next whole minute, add to time to first stop 
            
            if self.delay > 1 and current_depth > 50 # delay < 1 minute, deeper than 50fsw
                # round to next whole minute, add to bottom time, recompute decompression schedule
            
            
            
            self.stops = self._recalculate_stops(current_depth, elapsed)

    def next_stop(self) -> DecoStop

    def remaining_stops(self) -> list[DecoStop]

# ---------- DecoStop ----------
@dataclass
class DecoStop:
    depth_fsw: int
    planned_duration_min: int
    actual_duration_min: int = 0
    completed: bool = False

# ---------- AscentPhase ----------
class AscentPhase(DivePhase):
    def __init__(self, deco_plan: DecompressionPlan):
        super().__init__(name="Ascent", start_time=0, end_time=0, notes="")

    def tick(self, current_depth: int, elapsed_time: float) -> None:
        #called on each time update; delegates to deco_plan to check stop status and recompute if necessary
   
    def current_stop_status(self) -> dict: