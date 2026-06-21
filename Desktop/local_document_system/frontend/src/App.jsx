import SidePanel from "./Components/SidePanel";
import UploadFile from "./Components/UploadFile";
import View from "./Components/View";
import { Routes, Route, Navigate } from "react-router-dom";

const App = () => {
  return (
    <div className="flex h-screen bg-[var(--color-background)] overflow-hidden font-body">
      <SidePanel />
      <main className="flex-1 overflow-hidden p-4 md:p-6 lg:p-8 flex flex-col">
        <Routes>
          <Route path="/" element={<Navigate to="/home" replace />} />
          <Route path="/home" element={<View />} />
          <Route path="/upload" element={<UploadFile />} />
          <Route path="*" element={<Navigate to="/home" replace />} />
        </Routes>
      </main>
    </div>
  );
};

export default App;
