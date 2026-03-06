
import Card from "./Card";

export default function ScreenCard({ title, children }) {
  return (
    <Card>
      {title && (
        <div style={{marginBottom:"16px",fontWeight:"bold"}}>
          {title}
        </div>
      )}
      {children}
    </Card>
  );
}
