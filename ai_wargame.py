from __future__ import annotations
import argparse
import copy
from datetime import datetime
from enum import Enum
from dataclasses import dataclass, field
from time import sleep
from typing import Tuple, TypeVar, Type, Iterable, ClassVar, TextIO
import random
import requests

# maximum and minimum values for our heuristic scores (usually represents an end of game condition)
MAX_HEURISTIC_SCORE = 2000000000
MIN_HEURISTIC_SCORE = -2000000000

class UnitType(Enum):
    """Every unit type."""
    AI = 0
    Tech = 1
    Virus = 2
    Program = 3
    Firewall = 4

class Player(Enum):
    """The 2 players."""
    Attacker = 0
    Defender = 1

    def next(self) -> Player:
        """The next (other) player."""
        if self is Player.Attacker:
            return Player.Defender
        else:
            return Player.Attacker

class GameType(Enum):
    AttackerVsDefender = 0
    AttackerVsComp = 1
    CompVsDefender = 2
    CompVsComp = 3

class Heuristic(Enum):
    E0 = 0
    E1 = 1
    E2 = 2

##############################################################################################################

@dataclass(slots=True)
class Unit:
    player: Player = Player.Attacker
    type: UnitType = UnitType.Program
    health : int = 9
    # class variable: damage table for units (based on the unit type constants in order)
    damage_table : ClassVar[list[list[int]]] = [
        [3,3,3,3,1], # AI
        [1,1,6,1,1], # Tech
        [9,6,1,6,1], # Virus
        [3,3,3,3,1], # Program
        [1,1,1,1,1], # Firewall
    ]
    # class variable: repair table for units (based on the unit type constants in order)
    repair_table : ClassVar[list[list[int]]] = [
        [0,1,1,0,0], # AI
        [3,0,0,3,3], # Tech
        [0,0,0,0,0], # Virus
        [0,0,0,0,0], # Program
        [0,0,0,0,0], # Firewall
    ]

    def is_alive(self) -> bool:
        """Are we alive ?"""
        return self.health > 0

    def mod_health(self, health_delta : int):
        """Modify this unit's health by delta amount."""
        self.health += health_delta
        if self.health < 0:
            self.health = 0
        elif self.health > 9:
            self.health = 9

    def to_string(self) -> str:
        """Text representation of this unit."""
        p = self.player.name.lower()[0]
        t = self.type.name.upper()[0]
        return f"{p}{t}{self.health}"
    
    def __str__(self) -> str:
        """Text representation of this unit."""
        return self.to_string()
    
    def damage_amount(self, target: Unit) -> int:
        """How much can this unit damage another unit."""
        amount = self.damage_table[self.type.value][target.type.value]
        if target.health - amount < 0:
            return target.health
        return amount

    def repair_amount(self, target: Unit) -> int:
        """How much can this unit repair another unit."""
        amount = self.repair_table[self.type.value][target.type.value]
        if target.health + amount > 9:
            return 9 - target.health
        return amount

##############################################################################################################

@dataclass(slots=True)
class Coord:
    """Representation of a game cell coordinate (row, col)."""
    row : int = 0
    col : int = 0

    def col_string(self) -> str:
        """Text representation of this Coord's column."""
        coord_char = '?'
        if self.col < 16:
                coord_char = "0123456789abcdef"[self.col]
        return str(coord_char)

    def row_string(self) -> str:
        """Text representation of this Coord's row."""
        coord_char = '?'
        if self.row < 26:
                coord_char = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"[self.row]
        return str(coord_char)

    def to_string(self) -> str:
        """Text representation of this Coord."""
        return self.row_string()+self.col_string()
    
    def __str__(self) -> str:
        """Text representation of this Coord."""
        return self.to_string()
    
    def clone(self) -> Coord:
        """Clone a Coord."""
        return copy.copy(self)

    def iter_range(self, dist: int) -> Iterable[Coord]:
        """Iterates over Coords inside a rectangle centered on our Coord."""
        for row in range(self.row-dist,self.row+1+dist):
            for col in range(self.col-dist,self.col+1+dist):
                yield Coord(row,col)

    def iter_adjacent(self) -> Iterable[Coord]:
        """Iterates over adjacent Coords."""
        yield Coord(self.row-1,self.col)
        yield Coord(self.row,self.col-1)
        yield Coord(self.row+1,self.col)
        yield Coord(self.row,self.col+1)

    @classmethod
    def from_string(cls, s : str) -> Coord | None:
        """Create a Coord from a string. ex: D2."""
        s = s.strip()
        for sep in " ,.:;-_":
                s = s.replace(sep, "")
        if (len(s) == 2):
            coord = Coord()
            coord.row = "ABCDEFGHIJKLMNOPQRSTUVWXYZ".find(s[0:1].upper())
            coord.col = "0123456789abcdef".find(s[1:2].lower())
            return coord
        else:
            return None

##############################################################################################################

@dataclass(slots=True)
class CoordPair:
    """Representation of a game move or a rectangular area via 2 Coords."""
    src : Coord = field(default_factory=Coord)
    dst : Coord = field(default_factory=Coord)

    def to_string(self) -> str:
        """Text representation of a CoordPair."""
        return self.src.to_string()+" "+self.dst.to_string()
    
    def __str__(self) -> str:
        """Text representation of a CoordPair."""
        return self.to_string()

    def clone(self) -> CoordPair:
        """Clones a CoordPair."""
        return copy.copy(self)

    def iter_rectangle(self) -> Iterable[Coord]:
        """Iterates over cells of a rectangular area."""
        for row in range(self.src.row,self.dst.row+1):
            for col in range(self.src.col,self.dst.col+1):
                yield Coord(row,col)

    @classmethod
    def from_quad(cls, row0: int, col0: int, row1: int, col1: int) -> CoordPair:
        """Create a CoordPair from 4 integers."""
        return CoordPair(Coord(row0,col0),Coord(row1,col1))
    
    @classmethod
    def from_dim(cls, dim: int) -> CoordPair:
        """Create a CoordPair based on a dim-sized rectangle."""
        return CoordPair(Coord(0,0),Coord(dim-1,dim-1))
    
    @classmethod
    def from_string(cls, s : str) -> CoordPair | None:
        """Create a CoordPair from a string. ex: A3 B2"""
        s = s.strip()
        for sep in " ,.:;-_":
                s = s.replace(sep, "")
        if (len(s) == 4):
            coords = CoordPair()
            coords.src.row = "ABCDEFGHIJKLMNOPQRSTUVWXYZ".find(s[0:1].upper())
            coords.src.col = "0123456789abcdef".find(s[1:2].lower())
            coords.dst.row = "ABCDEFGHIJKLMNOPQRSTUVWXYZ".find(s[2:3].upper())
            coords.dst.col = "0123456789abcdef".find(s[3:4].lower())
            return coords
        else:
            return None

##############################################################################################################

@dataclass(slots=True)
class Options:
    """Representation of the game options."""
    dim: int = 5
    max_depth : int | None = 4
    min_depth : int | None = 2
    max_time : float | None = 5.0
    game_type : GameType = GameType.AttackerVsDefender
    alpha_beta : bool = True
    max_turns : int | None = 100
    randomize_moves : bool = True
    broker : str | None = None
    heuristic : Heuristic = Heuristic.E0

##############################################################################################################

@dataclass(slots=True)
class Stats:
    """Representation of the global game statistics."""
    evaluations_per_depth : dict[int,int] = field(default_factory=dict)
    total_seconds: float = 0.0

##############################################################################################################

@dataclass(slots=True)
class Game:
    """Representation of the game state."""
    file: TextIO | None = None
    board: list[list[Unit | None]] = field(default_factory=list)
    next_player: Player = Player.Attacker
    turns_played : int = 0
    options: Options = field(default_factory=Options)
    stats: Stats = field(default_factory=Stats)
    _attacker_has_ai : bool = True
    _defender_has_ai : bool = True

    def __post_init__(self):
        """Automatically called after class init to set up the default board state."""
        dim = self.options.dim
        self.board = [[None for _ in range(dim)] for _ in range(dim)]
        md = dim-1
        self.set(Coord(0,0),Unit(player=Player.Defender,type=UnitType.AI))
        self.set(Coord(1,0),Unit(player=Player.Defender,type=UnitType.Tech))
        self.set(Coord(0,1),Unit(player=Player.Defender,type=UnitType.Tech))
        self.set(Coord(2,0),Unit(player=Player.Defender,type=UnitType.Firewall))
        self.set(Coord(0,2),Unit(player=Player.Defender,type=UnitType.Firewall))
        self.set(Coord(1,1),Unit(player=Player.Defender,type=UnitType.Program))
        self.set(Coord(md,md),Unit(player=Player.Attacker,type=UnitType.AI))
        self.set(Coord(md-1,md),Unit(player=Player.Attacker,type=UnitType.Virus))
        self.set(Coord(md,md-1),Unit(player=Player.Attacker,type=UnitType.Virus))
        self.set(Coord(md-2,md),Unit(player=Player.Attacker,type=UnitType.Program))
        self.set(Coord(md,md-2),Unit(player=Player.Attacker,type=UnitType.Program))
        self.set(Coord(md-1,md-1),Unit(player=Player.Attacker,type=UnitType.Firewall))

        # File writing
        file_path = ("gameTrace-"
                     + str(self.options.alpha_beta) + "-"
                     + str(self.options.max_time) + "-"
                     + str(self.options.max_turns) + ".txt")
        self.file = open(file_path, "w")

        # write parameters
        self.file.write("Game parameters\n")
        self.file.write(f"The value of the timeout is {self.options.max_time}s\n")
        self.file.write(f"The max number of turns is {self.options.max_turns}\n")
        self.file.write(f"The alpha-beta is {self.options.alpha_beta}\n")
        self.file.write(f"The play mode is {self.options.game_type}\n")
        self.file.write(f"The name of the heuristic is {self.options.heuristic}\n")
        self.file.write("--------------------------------------------------\n\n")

    def clone(self) -> Game:
        """Make a new copy of a game for minimax recursion.

        Shallow copy of everything except the board (options and stats are shared).
        """
        new = copy.copy(self)
        new.board = copy.deepcopy(self.board)
        return new

    def is_empty(self, coord : Coord) -> bool:
        """Check if contents of a board cell of the game at Coord is empty (must be valid coord)."""
        return self.board[coord.row][coord.col] is None

    def get(self, coord : Coord) -> Unit | None:
        """Get contents of a board cell of the game at Coord."""
        if self.is_valid_coord(coord):
            return self.board[coord.row][coord.col]
        else:
            return None

    def set(self, coord : Coord, unit : Unit | None):
        """Set contents of a board cell of the game at Coord."""
        if self.is_valid_coord(coord):
            self.board[coord.row][coord.col] = unit

    def remove_dead(self, coord: Coord):
        """Remove unit at Coord if dead."""
        unit = self.get(coord)
        if unit is not None and not unit.is_alive():
            self.set(coord,None)
            if unit.type == UnitType.AI:
                if unit.player == Player.Attacker:
                    self._attacker_has_ai = False
                else:
                    self._defender_has_ai = False

    def mod_health(self, coord : Coord, health_delta : int):
        """Modify health of unit at Coord (positive or negative delta)."""
        target = self.get(coord)
        if target is not None:
            target.mod_health(health_delta)
            self.remove_dead(coord)

    def is_valid_move(self, coords : CoordPair) -> bool:
        if not self.is_valid_coord(coords.src) or not self.is_valid_coord(coords.dst):
            return False
        unit = self.get(coords.src)
        if unit is None or unit.player != self.next_player:
            return False
        unit = self.get(coords.dst)

        # Check self-destruct
        # Check if the source and destination coordinates are the same
        if coords.src == coords.dst:
            return True
        
        #Check for attacking
        #Check if there is a unit in the destination, and that it is a piece belonging to the turn player
        if (unit is not None) and (unit.player != self.next_player):
            #Checks if the pieces are either in the same col but 1 row apart, or if they're in the same row but 1 col apart
            if ((coords.src.col == coords.dst.col) and (abs(coords.src.row - coords.dst.row) == 1)) or ((coords.src.row == coords.dst.row) and (abs(coords.src.col - coords.dst.col) == 1)):
                return True
            
            else: 
                return False
            
        #Check for repairing
        #Checks that there is a unit in the destination, and that it is a piece belonging to the turn player
        if (unit is not None) and (unit.player == self.next_player):
            #Checks if they are either in the same col but 1 row apart, of ir they're in the same row but 1 col apart
            if ((coords.src.col == coords.dst.col) and (abs(coords.src.row - coords.dst.row) == 1)) or ((coords.src.row == coords.dst.row) and (abs(coords.src.col - coords.dst.col) == 1)):
                if (unit.health == 9):
                    return False
                
                #Checking all valid repair partners based on repair value table
                if (self.get(coords.src).type == UnitType.AI) and ((unit.type == UnitType.Virus) or (unit.type == UnitType.Tech)):
                    return True
                
                if (self.get(coords.src).type == UnitType.Tech) and ((unit.type == UnitType.AI) or (unit.type == UnitType.Firewall) or (unit.type == UnitType.Program)):
                    return True
                
                return False
            
            #Not in correct position
            else: 
                return False

        # Check general movement
        # Defender can move a Program, Firewall or AI unit down or right
        if((self.get(coords.src).player == Player.Defender) and 
           (self.get(coords.src).type == UnitType.AI or 
            self.get(coords.src).type == UnitType.Firewall or 
            self.get(coords.src).type == UnitType.Program)):
            
            # Check if unit is engaged in combat
            for coord in coords.src.iter_adjacent():
                if (self.is_valid_coord(coord) and not self.is_empty(coord) and self.get(coord).player != self.next_player):
                    return False
                
            # Check if unit moves down or right
            if ((coords.dst == Coord(coords.src.row+1,coords.src.col)) or 
                (coords.dst == Coord(coords.src.row,coords.src.col+1))):
                return True
            else:
                return False

        # Attacker can move a Program, Firewall or AI unit up or left
        if((self.get(coords.src).player == Player.Attacker) and 
           (self.get(coords.src).type == UnitType.AI or 
            self.get(coords.src).type == UnitType.Firewall or 
            self.get(coords.src).type == UnitType.Program)):
            
            # Check if unit is engaged in combat
            for coord in coords.src.iter_adjacent():
                if (self.is_valid_coord(coord) and not self.is_empty(coord) and (self.get(coord).player != self.next_player)):
                    return False
                
            # Check if unit moves up or left
            if ((coords.dst == Coord(coords.src.row-1,coords.src.col)) or 
                (coords.dst == Coord(coords.src.row,coords.src.col-1))):
                return True
            else:
                return False

        # Defender can move a Tech unit in any direction (except diagonally) at any time
        # Attacker can move a Virus unit in any direction (except diagonally) at any time 
        if ((coords.dst == Coord(coords.src.row-1,coords.src.col)) or 
            (coords.dst == Coord(coords.src.row,coords.src.col-1)) or 
            (coords.dst == Coord(coords.src.row+1,coords.src.col)) or 
            (coords.dst == Coord(coords.src.row,coords.src.col+1))):
            return True
        else:
            return False

    def perform_move(self, coords : CoordPair) -> Tuple[bool,str]:
        if self.is_valid_move(coords):
            # Movement: the destination coordinate is not occupied by any unit
            if self.get(coords.dst) is None:
                self.set(coords.dst,self.get(coords.src))
                self.set(coords.src,None)
                return (True,"move from " + str(coords.src) + " to " + str(coords.dst))
            # Self-destruct: the source and destination coordinates are the same
            elif coords.src == coords.dst:
                self.mod_health(coords.src, -9)
                total_damage = 0
                for coord in coords.src.iter_range(1):
                    if self.is_valid_coord(coord) and not self.is_empty(coord):
                        self.mod_health(coord, -2)
                        total_damage += 2
                return (True,"self-destruct at " + str(coords.src) + "\n"
                        "self-destructed for " + str(total_damage) + " total damage")
            # Repair: the source and destination belong to the same players
            elif self.get(coords.src).player == self.get(coords.dst).player:
                repair_amount = Unit.repair_table[self.get(coords.src).type.value][self.get(coords.dst).type.value]
                self.mod_health(coords.dst, repair_amount)
                return (True,"repair from " + str(coords.src) + " to " + str(coords.dst) + "\n"
                        "repaired " + str(repair_amount) + " health points")
            # Attack: the source and destination belong to opposing players
            else:
                dst_dmg = Unit.damage_table[self.get(coords.src).type.value][self.get(coords.dst).type.value]
                src_dmg = Unit.damage_table[self.get(coords.dst).type.value][self.get(coords.src).type.value]
                self.mod_health(coords.dst, -dst_dmg)
                self.mod_health(coords.src, -src_dmg)
                return (True, "attack from " + str(coords.src) + " to " + str(coords.dst) +
                        "\ncombat damage: to source =  " + str(src_dmg) + ", to target = " + str(dst_dmg))
        return (False,"invalid move")

    def next_turn(self):
        """Transitions game to the next turn."""
        self.next_player = self.next_player.next()
        self.turns_played += 1


    #Board is printed in here
    def to_string(self) -> str:
        """Pretty text representation of the game."""
        dim = self.options.dim
        output = ""
        output += f"Next player: {self.next_player.name}\n"
        output += f"Turns played: {self.turns_played}\n"
        coord = Coord()
        output += "\n   "
        for col in range(dim):
            coord.col = col
            label = coord.col_string()
            output += f"{label:^3} "
        output += "\n"
        for row in range(dim):
            coord.row = row
            label = coord.row_string()
            output += f"{label}: "
            for col in range(dim):
                coord.col = col
                unit = self.get(coord)
                if unit is None:
                    output += " .  "
                else:
                    output += f"{str(unit):^3} "
            output += "\n"

        self.file.write(output + "\n")
        return output

    def __str__(self) -> str:
        """Default string representation of a game."""
        return self.to_string()
    
    def is_valid_coord(self, coord: Coord) -> bool:
        """Check if a Coord is valid within out board dimensions."""
        dim = self.options.dim
        if coord.row < 0 or coord.row >= dim or coord.col < 0 or coord.col >= dim:
            return False
        return True

    def read_move(self) -> CoordPair:
        """Read a move from keyboard and return as a CoordPair."""
        while True:
            s = input(F'Player {self.next_player.name}, enter your move: ')
            coords = CoordPair.from_string(s)
            if coords is not None and self.is_valid_coord(coords.src) and self.is_valid_coord(coords.dst):
                return coords
            else:
                print('Invalid coordinates! Try again.')
    
    def human_turn(self):
        """Human player plays a move (or get via broker)."""
        if self.options.broker is not None:
            print("Getting next move with auto-retry from game broker...")
            while True:
                mv = self.get_move_from_broker()
                if mv is not None:
                    (success,result) = self.perform_move(mv)
                    print(f"Broker {self.next_player.name}: ",end='')
                    print(result)
                    self.file.write(result + "\n")
                    if success:
                        self.next_turn()
                        break
                sleep(0.1)
        else:
            while True:
                mv = self.read_move()
                (success,result) = self.perform_move(mv)
                if success:
                    print(f"Player {self.next_player.name}: ",end='')
                    print(result)
                    self.file.write(f"Player {self.next_player.name}: ")
                    self.file.write(result + "\n")
                    self.next_turn()
                    break
                else:
                    print("The move is not valid! Try again.")
                    self.file.write("The move is not valid! Try again.\n")

    def computer_turn(self) -> CoordPair | None:
        """Computer plays a move."""
        mv = self.suggest_move()
        if mv is not None:
            (success,result) = self.perform_move(mv)
            if success:
                print(f"Computer {self.next_player.name}: ",end='')
                print(result)
                self.file.write(f"Computer {self.next_player.name}: ")
                self.file.write(result + "\n")
                self.next_turn()
        return mv

    def player_units(self, player: Player) -> Iterable[Tuple[Coord,Unit]]:
        """Iterates over all units belonging to a player."""
        for coord in CoordPair.from_dim(self.options.dim).iter_rectangle():
            unit = self.get(coord)
            if unit is not None and unit.player == player:
                yield (coord,unit)

    def is_finished(self) -> bool:
        """Check if the game is over."""
        return self.has_winner() is not None

    def has_winner(self) -> Player | None:
        """Check if the game is over and returns winner"""
        if self.options.max_turns is not None and self.turns_played >= self.options.max_turns:
            return Player.Defender
        if self._attacker_has_ai:
            if self._defender_has_ai:
                return None
            else:
                return Player.Attacker    
        return Player.Defender

    def move_candidates(self) -> Iterable[CoordPair]:
        """Generate valid move candidates for the next player."""
        move = CoordPair()
        for (src,_) in self.player_units(self.next_player):
            move.src = src
            for dst in src.iter_adjacent():
                move.dst = dst
                if self.is_valid_move(move):
                    yield move.clone()
            move.dst = src
            yield move.clone()

    def e(self):
        # Use the heuristic corresponding to the selected option
        if self.options.heuristic == Heuristic.E1:
            return self.e1()
        elif self.options.heuristic == Heuristic.E2:
            return self.e2()
        else:
            return self.e0()

    #Fab's part
    #Heuristic e0
    def e0(self):
        #Define values for each unit type (adjust these values as needed)
        unit_values = {
            UnitType.AI: 9999,
            UnitType.Tech: 3,
            UnitType.Virus: 3,
            UnitType.Program: 3,
            UnitType.Firewall: 3,
        }

        #Initialize counters for each player's pieces and piece type
        player1_counts = {unit_type: 0 for unit_type in UnitType}
        player2_counts = {unit_type: 0 for unit_type in UnitType}

        #Count the number of each piece type for each player
        for coord in CoordPair.from_dim(self.options.dim).iter_rectangle():
            unit = self.get(coord)
            if unit is not None:
                if unit.player == Player.Attacker:
                    player1_counts[unit.type] += 1
                else:
                    player2_counts[unit.type] += 1


        e0_val = (
            sum(unit_values[unit_type] * player1_counts[unit_type] for unit_type in UnitType) 
            - sum(unit_values[unit_type] * player2_counts[unit_type] for unit_type in UnitType)
        )

        return e0_val
    
    #Sarah's part
    #Heuristic e1
    def e1(self):
        #Define values for each unit type (adjust these values as needed)
        unit_values = {
            UnitType.AI: 9999,
            UnitType.Tech: 500,
            UnitType.Virus: 500,
            UnitType.Program: 300,
            UnitType.Firewall: 50,
        }

        #Initialize counters for each player's pieces and piece type
        player1_counts = {unit_type: 0 for unit_type in UnitType}
        player2_counts = {unit_type: 0 for unit_type in UnitType}

        #Count the number of each piece type for each player
        for coord in CoordPair.from_dim(self.options.dim).iter_rectangle():
            unit = self.get(coord)
            if unit is not None:
                if unit.player == Player.Attacker:
                    player1_counts[unit.type] += 1
                else:
                    player2_counts[unit.type] += 1

        e1_val = (
            sum(unit_values[unit_type] * player1_counts[unit_type] for unit_type in UnitType) 
            - sum(unit_values[unit_type] * player2_counts[unit_type] for unit_type in UnitType)
        )

        return e1_val

    def e2(self):
        e2_val = 0

        # Calculate heuristic based on the total health of the player's units
        # Give more importance to the AI's health
        for coord in CoordPair.from_dim(self.options.dim).iter_rectangle():
            unit = self.get(coord)
            if unit is not None:
                if unit.player == Player.Attacker:
                    if unit.type == UnitType.AI:
                        e2_val += unit.health * 9999
                    else:
                        e2_val += unit.health
                else:
                    if unit.type == UnitType.AI:
                        e2_val -= unit.health * 9999
                    else:
                        e2_val -= unit.health

        return e2_val


    #Fab's part
    #Function to generate a list of all possible moves
    def generate_valid_moves(self):
        # This function generates all valid moves for the current player.
        # It returns a list of CoordPair objects.
        valid_moves = []
        for move in self.move_candidates():
            if self.is_valid_move(move):
                valid_moves.append(move)
        return valid_moves
    
    #Return should be: return (heuristic_score, move, avg_depth)
    #Fab's part
    def random_move(self, current_game, depth, maximize, start_time, current_depth = 0) -> Tuple[int, CoordPair | None, float]:
        elapsed_seconds = (datetime.now() - start_time).total_seconds()

        # Keep track of the num of evaluations at each depth level
        current_depth += 1
        if current_depth in self.stats.evaluations_per_depth:
            self.stats.evaluations_per_depth[current_depth] += 1
        else:
            self.stats.evaluations_per_depth[current_depth] = 1

        elapsed_seconds = (datetime.now() - start_time).total_seconds()

        if (self.is_finished()) or (depth == 0) or elapsed_seconds >= self.options.max_time - 0.01:
            return (current_game.e(), None, depth)
        
        #Attacker is the max
        if maximize:
            current_game.next_player = Player.Attacker
            max_eval = -float('inf')
            best_move = None

            for move in (current_game.generate_valid_moves()):
                game_clone = current_game.clone()
                game_clone.perform_move(move)
                #The , _ means only take the first return value
                eval, _, _ = current_game.random_move(game_clone, depth - 1, False, start_time, current_depth)

                if eval > max_eval:
                    max_eval = eval
                    best_move = move
            return (max_eval, best_move, depth)
        
        #Defender (minimizing player)
        else:
            current_game.next_player = Player.Defender
            min_eval = float('inf')
            best_move = None

            for move in (current_game.generate_valid_moves()):
                game_clone = current_game.clone()
                game_clone.perform_move(move)
                eval, _, _ = current_game.random_move(game_clone, depth - 1, True, start_time, current_depth)

                if eval < min_eval:
                    min_eval = eval
                    best_move = move
            return (min_eval, best_move, depth)
        



    #Sarah's part
    def alphabeta(self, current_game, depth, alpha, beta, maximize, start_time, current_depth = 0) -> Tuple[int, CoordPair | None, float]:

        # Keep track of the num of evaluations at each depth level
        current_depth += 1
        if current_depth in self.stats.evaluations_per_depth:
            self.stats.evaluations_per_depth[current_depth] += 1
        else:
            self.stats.evaluations_per_depth[current_depth] = 1

        elapsed_seconds = (datetime.now() - start_time).total_seconds()

        if (self.is_finished()) or (depth == 0) or elapsed_seconds >= self.options.max_time - 0.01:
            return (current_game.e(), None, depth)
        
        #Attacker
        if maximize:
            current_game.next_player = Player.Attacker
            max_eval = -float('inf')
            best_move = None

            for move in (current_game.generate_valid_moves()):
                game_clone = current_game.clone()
                game_clone.perform_move(move)
                eval, _, _ = current_game.alphabeta(game_clone, depth-1, alpha, beta, False, start_time, current_depth)
                if eval > max_eval:
                    max_eval = eval
                    best_move = move
                
                alpha = max(alpha,max_eval)

                if(max_eval >= beta):
                    break
            
            return (max_eval, best_move, depth)
        
        #Defender
        else:
            current_game.next_player = Player.Defender
            min_eval = float('inf')
            best_move = None

            for move in (current_game.generate_valid_moves()):
                game_clone = current_game.clone()
                game_clone.perform_move(move)
                eval, _, _ = current_game.alphabeta(game_clone, depth-1, alpha, beta, True, start_time, current_depth)
                if eval < min_eval:
                    min_eval = eval
                    best_move = move

                beta = min(beta,min_eval)

                if(min_eval <= alpha):
                    break
            return (min_eval, best_move, depth)

    def suggest_move(self) -> CoordPair | None:
        """Suggest the next move using minimax alpha beta. TODO: REPLACE RANDOM_MOVE WITH PROPER GAME LOGIC!!!""" #########################################################
        start_time = datetime.now()
        
        #Set boolean for maximize depending on player
        if self.next_player == Player.Attacker:
            maximize = True
        else:
            maximize = False

        #Check if we are playing using alpha-beta
        if self.options.alpha_beta == False:
            (score, move, avg_depth) = self.random_move(self.clone(), 6, maximize, start_time)
        else:
            (score, move, avg_depth) = self.alphabeta(self.clone(), 10, MIN_HEURISTIC_SCORE, MAX_HEURISTIC_SCORE, maximize, start_time)

        elapsed_seconds = (datetime.now() - start_time).total_seconds()
        self.stats.total_seconds += elapsed_seconds
        total_evals = sum(self.stats.evaluations_per_depth.values())

        print(f"Heuristic score: {score}")
        self.file.write(f"Heuristic score: {score}\n")
        print(f"Cumulative evals: {total_evals}")
        self.file.write(f"Cumulative evals: {total_evals}\n")
        print(f"Cumulative % evals by depth: ",end='')
        self.file.write(f"Cumulative % evals by depth: ")
        for k in sorted(self.stats.evaluations_per_depth.keys()):
            print(f"{k}={self.stats.evaluations_per_depth[k]/total_evals*100:0.1f}% ",end='')
            self.file.write(f"{k}={self.stats.evaluations_per_depth[k]/total_evals*100:0.1f}% ")
        print()
        print(f"Cumulative evals per depth: ",end='')
        self.file.write(f"\nCumulative evals per depth: ")
        for k in sorted(self.stats.evaluations_per_depth.keys()):
            print(f"{k}={self.stats.evaluations_per_depth[k]} ",end='')
            self.file.write(f"{k}={self.stats.evaluations_per_depth[k]} ")
        print()
        print(f"Elapsed time: {elapsed_seconds:0.1f}s")
        self.file.write(f"\nElapsed time: {elapsed_seconds:0.1f}s\n")

        return move

    def post_move_to_broker(self, move: CoordPair):
        """Send a move to the game broker."""
        if self.options.broker is None:
            return
        data = {
            "from": {"row": move.src.row, "col": move.src.col},
            "to": {"row": move.dst.row, "col": move.dst.col},
            "turn": self.turns_played
        }
        try:
            r = requests.post(self.options.broker, json=data)
            if r.status_code == 200 and r.json()['success'] and r.json()['data'] == data:
                # print(f"Sent move to broker: {move}")
                pass
            else:
                print(f"Broker error: status code: {r.status_code}, response: {r.json()}")
        except Exception as error:
            print(f"Broker error: {error}")

    def get_move_from_broker(self) -> CoordPair | None:
        """Get a move from the game broker."""
        if self.options.broker is None:
            return None
        headers = {'Accept': 'application/json'}
        try:
            r = requests.get(self.options.broker, headers=headers)
            if r.status_code == 200 and r.json()['success']:
                data = r.json()['data']
                if data is not None:
                    if data['turn'] == self.turns_played+1:
                        move = CoordPair(
                            Coord(data['from']['row'],data['from']['col']),
                            Coord(data['to']['row'],data['to']['col'])
                        )
                        print(f"Got move from broker: {move}")
                        return move
                    else:
                        # print("Got broker data for wrong turn.")
                        # print(f"Wanted {self.turns_played+1}, got {data['turn']}")
                        pass
                else:
                    # print("Got no data from broker")
                    pass
            else:
                print(f"Broker error: status code: {r.status_code}, response: {r.json()}")
        except Exception as error:
            print(f"Broker error: {error}")
        return None




##############################################################################################################

def main():
    # parse command line arguments
    parser = argparse.ArgumentParser(
        prog='ai_wargame',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('--max_depth', type=int, help='maximum search depth')
    parser.add_argument('--max_time', type=float, help='maximum search time')
    parser.add_argument('--game_type', type=str, default="auto", help='game type: auto|attacker|defender|manual')
    parser.add_argument('--broker', type=str, help='play via a game broker')
    parser.add_argument('--max_turns', type=int, help='maximum number of moves/turns')
    parser.add_argument('--e', type=int, help='heuristic number: 0|1|2')
    args = parser.parse_args()

    # parse the game type
    if args.game_type == "attacker":
        game_type = GameType.AttackerVsComp
    elif args.game_type == "defender":
        game_type = GameType.CompVsDefender
    elif args.game_type == "manual":
        game_type = GameType.AttackerVsDefender
    else:
        game_type = GameType.CompVsComp

    # set up game options
    options = Options(game_type=game_type)

    # override class defaults via command line options
    if args.max_depth is not None:
        options.max_depth = args.max_depth
    if args.max_time is not None:
        options.max_time = args.max_time
    if args.broker is not None:
        options.broker = args.broker
    if args.max_turns is not None:
        options.max_turns = args.max_turns
    if args.e is not None:
        options.heuristic = Heuristic(args.e)

    # create a new game
    game = Game(options=options)

    # the main game loop
    while True:
        print()
        print(game)
        winner = game.has_winner()
        if winner is not None:
            print(f"{winner.name} wins in {game.turns_played} moves!")
            game.file.write(f"{winner.name} wins in {game.turns_played} moves!")
            break
        if game.options.game_type == GameType.AttackerVsDefender:
            game.human_turn()
        elif game.options.game_type == GameType.AttackerVsComp and game.next_player == Player.Attacker:
            game.human_turn()
        elif game.options.game_type == GameType.CompVsDefender and game.next_player == Player.Defender:
            game.human_turn()
        else:
            player = game.next_player
            move = game.computer_turn()
            if move is not None:
                game.post_move_to_broker(move)
            else:
                print("Computer doesn't know what to do!!!")
                exit(1)



##############################################################################################################

if __name__ == '__main__':
    main()
